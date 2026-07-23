"""
Resume KB Builder — V3.2.1 知识库构建
分块 → Embedding → FAISS索引 → Metadata
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np
from loguru import logger

from src.llm.router import EmbeddingClient


class ResumeKB:
    """
    简历知识库
    结构: raw/ → chunks/ → embeddings/index.faiss → metadata/metadata.json
    """

    CHUNK_TYPES = ["skills", "project", "quant_achievement", "education", "summary"]

    def __init__(self, kb_dir: str | Path | None = None):
        if kb_dir is None:
            kb_dir = Path(__file__).parent / "resume_kb"
        self._dir = Path(kb_dir)
        for sub in ["raw", "chunks", "embeddings", "metadata"]:
            (self._dir / sub).mkdir(parents=True, exist_ok=True)
        self._embedding = EmbeddingClient()
        self._index: Optional[faiss.IndexFlatIP] = None
        self._metadata: List[Dict[str, Any]] = []
        self._load()

    # ─── 构建 ────────────────────────────────────────────

    def add_resume(self, resume_text: str, source: str = "synthetic",
                   tags: List[str] | None = None) -> int:
        """添加一份简历到知识库，返回 chunk 数量"""
        chunks = self._chunk_resume(resume_text)
        if not chunks:
            return 0

        # 保存 raw
        raw_name = f"resume_{int(time.time())}_{source}.md"
        (self._dir / "raw" / raw_name).write_text(resume_text, encoding="utf-8")

        # 保存 chunks
        for i, chunk in enumerate(chunks):
            chunk_name = f"{raw_name.replace('.md','')}_chunk{i:03d}.json"
            (self._dir / "chunks" / chunk_name).write_text(
                json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")

        # 向量化（直接用 TF-IDF，DeepSeek 无公开 Embedding API）
        texts = [c["text"] for c in chunks]
        vectors = self._tfidf_embed(texts, dim=256)
        vectors_np = np.array(vectors, dtype=np.float32)

        # L2 归一化（内积 → 余弦相似度）
        faiss.normalize_L2(vectors_np)

        if self._index is None:
            dim = vectors_np.shape[1]
            self._index = faiss.IndexFlatIP(dim)

        start_idx = len(self._metadata)
        self._index.add(vectors_np)

        # Metadata
        for i, chunk in enumerate(chunks):
            self._metadata.append({
                "id": start_idx + i,
                "chunk_file": f"{raw_name.replace('.md','')}_chunk{i:03d}.json",
                "source": source,
                "chunk_type": chunk["type"],
                "keywords": chunk.get("keywords", []),
                "tags": tags or [],
            })

        self._save()
        logger.info(f"Resume KB: +{len(chunks)} chunks (total: {len(self._metadata)})")
        return len(chunks)

    def _chunk_resume(self, text: str) -> List[Dict[str, Any]]:
        """将简历文本分块"""
        chunks = []

        # 1. 技能块
        skills_match = re.findall(r'[-*]\s*(.+?)[:：]\s*(.+?)(?:\n|$)', text)
        if skills_match:
            skills_text = "技能: " + "; ".join(f"{k}={v}" for k, v in skills_match)
            chunks.append({"type": "skills", "text": skills_text, "keywords": [k.strip() for k, _ in skills_match]})

        # 2. 项目经历块
        project_sections = re.split(r'(?:##\s*项目|###\s*项目|项目经历|Project)', text, flags=re.IGNORECASE)
        for section in project_sections[1:]:
            section = section.strip()[:500]
            if section:
                techs = re.findall(r'[A-Z][a-zA-Z+#.]+(?:\s*[·/,]\s*[A-Z][a-zA-Z+#.]+)*', section)
                chunks.append({"type": "project", "text": section, "keywords": techs})

        # 3. 量化成果块
        quant_patterns = [
            r'(\d+[万亿千百]?\s*(?:%|QPS|倍|人|个|条|次|万|亿))',
            r'(?:提升|降低|优化|减少|增加|缩短).*?(\d+[%万亿千百]?)',
        ]
        quant_parts = []
        for pat in quant_patterns:
            quant_parts.extend(re.findall(pat, text, re.IGNORECASE))
        if quant_parts:
            quant_text = "量化成果: " + "; ".join(quant_parts[:10])
            chunks.append({"type": "quant_achievement", "text": quant_text, "keywords": quant_parts})

        # 4. 教育背景块
        edu_match = re.search(r'(?:教育|学历|Education).*?(?=\n\n|\n##|\Z)', text, re.DOTALL | re.IGNORECASE)
        if edu_match:
            chunks.append({"type": "education", "text": edu_match.group(0)[:300], "keywords": []})

        # 5. 整体摘要块（前300字）
        summary = text[:300].strip()
        if summary:
            chunks.append({"type": "summary", "text": summary, "keywords": []})

        return chunks

    # ─── 检索 ────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5,
               chunk_types: List[str] | None = None,
               min_similarity: float = 0.5) -> List[Dict[str, Any]]:
        """语义检索"""
        if self._index is None or len(self._metadata) == 0:
            return []

        query_vec = np.array(self._tfidf_embed([query], dim=self._index.d), dtype=np.float32)
        faiss.normalize_L2(query_vec)

        # 搜索更多（后续过滤）
        search_k = min(top_k * 3, len(self._metadata))
        scores, indices = self._index.search(query_vec, search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            if chunk_types and meta["chunk_type"] not in chunk_types:
                continue
            if float(score) < min_similarity:
                continue

            # 加载 chunk 文本
            chunk_path = self._dir / "chunks" / meta["chunk_file"]
            chunk_text = ""
            if chunk_path.exists():
                chunk_data = json.loads(chunk_path.read_text(encoding="utf-8"))
                chunk_text = chunk_data.get("text", "")

            results.append({
                "id": int(idx),
                "score": float(score),
                "type": meta["chunk_type"],
                "text": chunk_text,
                "keywords": meta.get("keywords", []),
            })

            if len(results) >= top_k:
                break

        return results

    def keyword_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """BM25 风格关键词检索（简化版：关键词交集 + TF）"""
        query_terms = set(query.lower().split())
        if not query_terms:
            return []

        scored = []
        for meta in self._metadata:
            # 加载文本
            chunk_path = self._dir / "chunks" / meta["chunk_file"]
            if not chunk_path.exists():
                continue
            chunk_data = json.loads(chunk_path.read_text(encoding="utf-8"))
            text = chunk_data.get("text", "").lower()

            # 简单 TF 分数
            score = sum(text.count(term) for term in query_terms)
            if score > 0:
                scored.append({
                    "id": meta["id"],
                    "score": score,
                    "type": meta["chunk_type"],
                    "text": chunk_data.get("text", ""),
                    "keywords": meta.get("keywords", []),
                })

        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    def hybrid_search(self, query: str, top_k: int = 5,
                      semantic_weight: float = 0.45,
                      keyword_weight: float = 0.35,
                      metadata_weight: float = 0.20,
                      chunk_types: List[str] | None = None) -> List[Dict[str, Any]]:
        """
        Hybrid 检索: Final = semantic*0.45 + keyword*0.35 + metadata*0.20
        """
        semantic_results = self.search(query, top_k=top_k * 2, chunk_types=chunk_types)
        keyword_results = self.keyword_search(query, top_k=top_k * 2)

        # 合并 + 去重
        merged: Dict[int, Dict[str, Any]] = {}

        # 归一化语义分
        max_sem = max((r["score"] for r in semantic_results), default=1.0)
        for r in semantic_results:
            merged[r["id"]] = {"data": r, "semantic": r["score"] / max(max_sem, 0.01), "keyword": 0.0}

        # 归一化关键词分
        max_kw = max((r["score"] for r in keyword_results), default=1.0)
        for r in keyword_results:
            if r["id"] in merged:
                merged[r["id"]]["keyword"] = r["score"] / max(max_kw, 0.01)
            else:
                merged[r["id"]] = {"data": r, "semantic": 0.0, "keyword": r["score"] / max(max_kw, 0.01)}

        # 最终加权 + Metadata boost
        final = []
        for item in merged.values():
            meta = self._metadata[item["data"]["id"]] if item["data"]["id"] < len(self._metadata) else {}
            # Metadata boost: 有 tag 匹配 +0.1
            meta_boost = 0.0
            query_lower = query.lower()
            for tag in meta.get("tags", []):
                if tag.lower() in query_lower:
                    meta_boost = 0.1
                    break

            score = (semantic_weight * item["semantic"] +
                     keyword_weight * item["keyword"] +
                     metadata_weight * meta_boost)
            item["data"]["hybrid_score"] = round(score, 3)
            final.append(item["data"])

        final.sort(key=lambda x: -x["hybrid_score"])
        return final[:top_k]

    def _tfidf_embed(self, texts: List[str], dim: int = 256) -> List[List[float]]:
        """TF-IDF 风格词袋向量（fallback）"""
        from collections import Counter
        # 构建全局词汇表
        all_words: List[str] = []
        for t in texts:
            all_words.extend(t.lower().split())
        word_freq = Counter(all_words)
        vocab = [w for w, _ in word_freq.most_common(dim)]

        vectors = []
        for t in texts:
            words = t.lower().split()
            word_count = Counter(words)
            vec = [word_count.get(w, 0) / max(len(words), 1) for w in vocab]
            # 填充到 dim
            while len(vec) < dim:
                vec.append(0.0)
            vectors.append(vec[:dim])
        return vectors

    # ─── 持久化 ──────────────────────────────────────────

    def _save(self) -> None:
        """保存 FAISS 索引 + metadata"""
        if self._index is not None:
            faiss.write_index(self._index, str(self._dir / "embeddings" / "index.faiss"))
        (self._dir / "metadata" / "metadata.json").write_text(
            json.dumps(self._metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        index_path = self._dir / "embeddings" / "index.faiss"
        meta_path = self._dir / "metadata" / "metadata.json"
        if index_path.exists():
            self._index = faiss.read_index(str(index_path))
        if meta_path.exists():
            self._metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    @property
    def stats(self) -> dict:
        return {
            "total_chunks": len(self._metadata),
            "chunk_types": {t: sum(1 for m in self._metadata if m["chunk_type"] == t) for t in self.CHUNK_TYPES},
            "has_index": self._index is not None,
        }
