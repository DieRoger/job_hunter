"""
JD Analysis Agent — 提取 + 标准化职位描述
"""

from __future__ import annotations

import json
from typing import Any

from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor
from src.models.schemas import JobDescription
from src.utils.registry import PromptRegistry
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class JDAnalysisAgent(BaseAgent):
    """JD 分析 Agent"""

    name = "jd_analysis_agent"
    description = "提取 JD 关键信息并标准化"

    def __init__(self):
        self._llm = get_llm_client()
        self._prompts = PromptRegistry.get_instance()
        self._cost = CostMonitor.get_instance()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        jd_text = kwargs.get("jd_text", "")
        if not jd_text:
            return AgentResult.fail("未提供 JD 文本")

        prompt = self._prompts.render("jd_analysis", jd_text=jd_text)
        response = self._llm.json(prompt)

        self._cost.record(
            task="jd_analysis",
            model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms,
            cost_usd=response.cost_usd,
        )

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            return AgentResult.fail(f"JD 分析 JSON 无效: {e}")

        jd = JobDescription(
            title=data.get("title", ""),
            education=data.get("education", ""),
            experience_years=data.get("experience_years", 0),
            hard_skills=data.get("hard_skills", []),
            soft_skills=data.get("soft_skills", []),
            bonus_points=data.get("bonus_points", []),
            industry=data.get("industry", ""),
            keywords=data.get("keywords", []),
            raw_text=jd_text,
        )
        # 合并技能列表
        jd.skills_required = jd.hard_skills + jd.soft_skills

        return AgentResult.ok(jd, tokens=response.total_tokens)
