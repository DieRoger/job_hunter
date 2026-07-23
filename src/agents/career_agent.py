"""
Career Agent — 5个岗位方向推荐 + 学习路径 + 项目建议
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor
from src.models.schemas import CareerDirection, LearningItem, ProjectSuggestion, UserProfile
from src.repository.store import ProfileRepository
from src.utils.registry import PromptRegistry
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class CareerAgent(BaseAgent):
    """岗位方向推荐 Agent"""

    name = "career_agent"
    description = "基于用户画像推荐5个岗位方向，包含学习路径和项目建议"

    def __init__(self):
        self._llm = get_llm_client()
        self._prompts = PromptRegistry.get_instance()
        self._cost = CostMonitor.get_instance()
        self._repo = ProfileRepository()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        profile_name = kwargs.get("profile_name", "default")

        # 加载用户画像
        profile_data = self._repo.load(profile_name)
        if profile_data is None:
            return AgentResult.fail(f"用户画像不存在: {profile_name}，请先运行 job-hunter init")

        profile = UserProfile(**profile_data)
        logger.info(f"为用户 '{profile.name}' 生成岗位方向推荐")

        # 使用 reasoner 模型（复杂推理任务）
        from src.llm.router import LLMRouter
        router = LLMRouter(self._llm)
        model = router.resolve_model("career_discover")

        # 渲染 Prompt
        prompt = self._prompts.render("discover", user_profile=json.dumps(
            profile.model_dump(), ensure_ascii=False, indent=2
        ))

        response = self._llm.json(prompt, model=model)

        # 记录成本
        self._cost.record(
            task="career_discover",
            model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms,
            cost_usd=response.cost_usd,
        )

        # 解析
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            return AgentResult.fail(f"LLM 返回格式无效: {e}")

        directions = self._parse_directions(data.get("directions", []))
        logger.info(f"生成 {len(directions)} 个岗位方向推荐")

        return AgentResult.ok(
            directions,
            tokens=response.total_tokens,
            duration_ms=response.duration_ms,
        )

    def _parse_directions(self, raw: list[dict]) -> list[CareerDirection]:
        result = []
        for item in raw:
            direction = CareerDirection(
                title=item.get("title", ""),
                match_score=item.get("match_score", 0),
                match_reason=item.get("match_reason", ""),
                skill_gaps=item.get("skill_gaps", []),
                resume_advice=item.get("resume_advice", ""),
                learning_path=[
                    LearningItem(
                        topic=lp.get("topic", ""),
                        resource=lp.get("resource", ""),
                        estimated_hours=lp.get("estimated_hours", 0),
                        priority=lp.get("priority", "medium"),
                    )
                    for lp in item.get("learning_path", [])
                ],
                suggested_projects=[
                    ProjectSuggestion(
                        name=p.get("name", ""),
                        description=p.get("description", ""),
                        tech_stack=p.get("tech_stack", []),
                        difficulty=p.get("difficulty", "中等"),
                    )
                    for p in item.get("suggested_projects", [])
                ],
                timeline=item.get("timeline", ""),
            )
            result.append(direction)
        return result
