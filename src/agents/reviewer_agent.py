"""
Reviewer Agent — AI 输出二次审核，提升结果质量
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor
from src.models.schemas import CareerDirection, JobDescription
from src.utils.registry import PromptRegistry
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class ReviewerAgent(BaseAgent):
    """质量审核 Agent — 对 Career 和 JD Analysis 输出做二次审核"""

    name = "reviewer_agent"
    description = "审核 AI 输出质量，过滤低质量/不合理结果"

    def __init__(self):
        self._llm = get_llm_client()
        self._prompts = PromptRegistry.get_instance()
        self._cost = CostMonitor.get_instance()

    def review_career_directions(
        self, ctx: WorkflowContext, directions: list[CareerDirection]
    ) -> list[CareerDirection]:
        """审核岗位方向推荐，过滤匹配度过低或明显不合理的"""
        filtered = []
        for d in directions:
            # 匹配度过低
            if d.match_score < 50:
                logger.warning(f"Reviewer 过滤低分方向: {d.title} ({d.match_score})")
                continue
            # 没有匹配理由
            if not d.match_reason or len(d.match_reason) < 20:
                logger.warning(f"Reviewer 过滤无理由方向: {d.title}")
                continue
            filtered.append(d)

        if len(filtered) < 3:
            logger.warning(f"过滤后方向不足3个，保留全部原始推荐")
            return directions

        return filtered

    def review_jd_analysis(
        self, ctx: WorkflowContext, jd: JobDescription, original_text: str
    ) -> JobDescription:
        """审核 JD 分析结果，检查技能提取完整性"""
        # 如果提取的技能太少，可能遗漏
        if len(jd.hard_skills) < 3:
            logger.warning(f"JD 硬技能提取过少 ({len(jd.hard_skills)}项)，疑似遗漏")
            jd.raw_text = original_text  # 保留原始文本供后续使用

        return jd

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        """通用执行入口（通常不直接使用，而是调用具体 review 方法）"""
        return AgentResult.ok(None, warnings=["ReviewerAgent 请使用具体 review 方法"])
