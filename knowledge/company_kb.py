"""
Company Knowledge Base — V3.2.2
首次 LLM 抓取 → JSON 缓存 7 天 → 全 Agent 共享
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor


class CompanyKB:
    """公司知识库 — 缓存 + 过期策略"""

    CACHE_TTL = 7 * 24 * 3600  # 7天
    FIELDS = ["business", "tech_stack", "departments", "interview_style",
              "salary_range", "hiring_trend", "culture", "competitors", "recent_news"]

    def __init__(self, kb_dir: str | Path | None = None):
        if kb_dir is None:
            kb_dir = Path(__file__).parent / "companies"
        self._dir = Path(kb_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._llm = get_llm_client()
        self._cost = CostMonitor.get_instance()

    def get(self, company: str, force_refresh: bool = False) -> Dict[str, Any]:
        """获取公司知识（缓存优先）"""
        cache_path = self._cache_path(company)

        # 检查缓存
        if not force_refresh and cache_path.exists():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            age = time.time() - data.get("cached_at", 0)
            if age < self.CACHE_TTL:
                logger.debug(f"CompanyKB 缓存命中: {company} ({age/3600:.1f}h前)")
                return data

        # 抓取
        logger.info(f"CompanyKB 抓取: {company}")
        data = self._fetch(company)
        data["cached_at"] = time.time()
        data["company"] = company

        cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def _fetch(self, company: str) -> Dict[str, Any]:
        """LLM 抓取公司信息"""
        prompt = f"""请提供关于"{company}"公司的以下信息。每条30-80字，如果不确定写"暂无公开信息"。

1. 主营业务 (business)
2. 技术栈 (tech_stack)
3. 主要部门 (departments)
4. 面试风格 (interview_style)
5. 薪资范围 (salary_range)
6. 招聘趋势 (hiring_trend)
7. 企业文化 (culture)
8. 主要竞品 (competitors)
9. 近期动态 (recent_news)

输出JSON格式: {{"business":"...", "tech_stack":"...", ...}}"""

        resp = self._llm.json(prompt)
        self._cost.record(task="company_kb", model=resp.model,
                          prompt_tokens=resp.usage.get("prompt_tokens", 0),
                          completion_tokens=resp.usage.get("completion_tokens", 0),
                          duration_ms=resp.duration_ms, cost_usd=resp.cost_usd)

        try:
            return json.loads(resp.content)
        except json.JSONDecodeError:
            return {f: "获取失败" for f in self.FIELDS}

    def summary_for_greeting(self, company: str) -> str:
        """生成招呼语可用的公司信息摘要（100字内）"""
        data = self.get(company)
        parts = []
        if data.get("business"):
            parts.append(f"{company}主营{data['business'][:40]}")
        if data.get("tech_stack"):
            parts.append(f"技术栈: {data['tech_stack'][:40]}")
        if data.get("culture"):
            parts.append(f"文化: {data['culture'][:30]}")
        return "。".join(parts)[:120]

    def summary_for_interview(self, company: str) -> str:
        """生成面试准备信息"""
        data = self.get(company)
        return f"面试风格: {data.get('interview_style','暂无')}。{data.get('recent_news','')[:80]}"

    def _cache_path(self, company: str) -> Path:
        safe = company.replace("/", "-").replace("\\", "-").replace(" ", "_")
        return self._dir / f"{safe}.json"

    def clear_cache(self, company: str | None = None) -> None:
        """清除缓存"""
        if company:
            p = self._cache_path(company)
            if p.exists():
                p.unlink()
        else:
            for f in self._dir.glob("*.json"):
                f.unlink()

    @property
    def cached_companies(self) -> list[str]:
        return [p.stem for p in self._dir.glob("*.json")]
