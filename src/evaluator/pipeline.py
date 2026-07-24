"""
SearchPipeline — 搜索流水线
采集 → 去重 → Embedding → Rule → Graph → LLM → 排序
"""

from __future__ import annotations

from loguru import logger

from src.evaluator.scorer import MatchScorer
from src.llm.router import EmbeddingClient
from src.models.schemas import JobDescription, MatchResult, UserProfile


class SearchPipeline:
    """搜索流水线：多步处理 → 智能排序"""

    def __init__(self, embedding: EmbeddingClient | None = None):
        self._scorer = MatchScorer()
        self._embedding = embedding or EmbeddingClient()

    def run(
        self,
        profile: UserProfile,
        raw_jobs: list[JobDescription],
        top_k: int = 20,
        min_score: float = 50.0,
    ) -> list[MatchResult]:
        """
        完整搜索流水线：
        1. Normalize — 标准化JD
        2. Deduplicate — 去重
        3. Embedding pre-filter — 向量粗筛（可选，加速）
        4. Triple Score — Rule + Graph + LLM
        5. Sort — 按final_score降序
        """
        logger.info(f"SearchPipeline: {len(raw_jobs)} raw → normalize → deduplicate → score → top{top_k}")

        # 1. Normalize (已在 JD 中保留 raw_text)
        normalized = [self._normalize(j) for j in raw_jobs]

        # 2. Deduplicate — 基于标题+公司去重
        deduped = self._deduplicate(normalized)

        # 3. Score (三元评分)
        scored = self._scorer.score_batch(profile, deduped, min_score=min_score)

        # 4. Sort
        scored.sort(key=lambda r: r.final_score, reverse=True)

        # 5. Top-K
        result = scored[:top_k]

        logger.info(
            f"SearchPipeline 完成: {len(raw_jobs)}→{len(normalized)}→{len(deduped)}→{len(scored)}→{len(result)}"
        )
        return result

    def _normalize(self, jd: JobDescription) -> JobDescription:
        """标准化JD — 填充缺失字段"""
        if not jd.skills_required and jd.hard_skills:
            jd.skills_required = list(jd.hard_skills)
        if not jd.title:
            jd.title = jd.raw_text[:50] if jd.raw_text else "未知岗位"
        return jd

    def _deduplicate(self, jobs: list[JobDescription]) -> list[JobDescription]:
        """去重 — 同公司+同岗位只保留一个"""
        seen: set[str] = set()
        result = []
        for jd in jobs:
            key = f"{jd.company.strip().lower()}|{jd.title.strip().lower()}"
            if key in seen:
                continue
            seen.add(key)
            result.append(jd)
        if len(jobs) > len(result):
            logger.info(f"去重: {len(jobs)} → {len(result)} (移除 {len(jobs)-len(result)} 个重复)")
        return result

    def embedding_prefilter(
        self, profile: UserProfile, jobs: list[JobDescription], top_k: int = 50
    ) -> list[JobDescription]:
        """
        Embedding 粗筛 — 用向量相似度快速过滤（减少后续LLM调用）
        """
        if not jobs:
            return []

        profile_text = f"{profile.current_position} {profile.summary} {' '.join(s.name for s in profile.skills[:10])}"
        profile_vec = self._embedding.embed(profile_text)

        scored = []
        for jd in jobs:
            skills_str = " ".join(
                jd.skills_required[:10] if jd.skills_required else jd.hard_skills[:10]
            )
            jd_text = f"{jd.title} {jd.description[:200]} {skills_str}"
            jd_vec = self._embedding.embed(jd_text)
            sim = self._embedding.similarity(profile_vec, jd_vec)
            scored.append((sim, jd))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [jd for _, jd in scored[:top_k]]


class DedupUtil:
    """去重工具"""

    @staticmethod
    def title_similarity(a: str, b: str) -> float:
        """标题相似度（简单Jaccard）"""
        set_a = set(a.lower().split())
        set_b = set(b.lower().split())
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    @staticmethod
    def fuzzy_deduplicate(jobs: list[JobDescription], threshold: float = 0.8) -> list[JobDescription]:
        """模糊去重 — 标题相似度 > threshold 视为重复"""
        result: list[JobDescription] = []
        for jd in jobs:
            is_dup = False
            for existing in result:
                sim = DedupUtil.title_similarity(jd.title, existing.title)
                if sim > threshold and jd.company.strip().lower() == existing.company.strip().lower():
                    is_dup = True
                    break
            if not is_dup:
                result.append(jd)
        return result
