"""
Judge + Critic Agent — V3.15 评测核心
Judge: 对任意Agent输出打分 + 评分理由
Critic: 给出具体修改建议（非笼统反馈）
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class JudgeAgent(BaseAgent):
    """
    评分 Agent — 对任意输出打分
    输出: { score: 0-100, dimensions: {...}, reason: "..." }
    """

    name = "judge"
    description = "对Agent输出质量打分，多维度评估"

    DIMENSIONS = {
        "resume_optimize": ["关键词匹配", "量化程度", "结构清晰", "真实性保持", "针对性"],
        "greeting": ["个性化", "匹配点突出", "长度控制", "自然度", "吸引力"],
        "discover": ["匹配度合理", "建议实用性", "方向多样性", "理由充分"],
        "jd_analysis": ["技能提取完整", "要求识别准确", "结构化程度"],
    }

    def __init__(self):
        self._llm = get_llm_client()
        self._cost = CostMonitor.get_instance()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        task_type = kwargs.get("task_type", "resume_optimize")
        input_data = kwargs.get("input_data", {})
        output_data = kwargs.get("output_data", {})
        dimensions = kwargs.get("dimensions", self.DIMENSIONS.get(task_type, ["综合质量"]))

        prompt = self._build_prompt(task_type, input_data, output_data, dimensions)
        response = self._llm.json(prompt)

        self._cost.record(
            task="judge", model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms, cost_usd=response.cost_usd,
        )

        try:
            result = json.loads(response.content)
        except json.JSONDecodeError:
            return AgentResult.fail("Judge JSON 无效")

        return AgentResult.ok(result, tokens=response.total_tokens)

    def _build_prompt(self, task_type: str, input_data: dict, output_data: dict,
                      dimensions: list[str]) -> str:
        dim_str = "\n".join(f"- {d} (0-100)" for d in dimensions)
        return f"""你是严格的评测专家。对以下{task_type}任务的输出打分。

# 评分维度
{dim_str}

# 输入
{json.dumps(input_data, ensure_ascii=False, indent=2)[:1500]}

# 输出
{json.dumps(output_data, ensure_ascii=False, indent=2)[:1500]}

# 输出格式
{{
  "score": 75,
  "dimensions": {{"关键词匹配": 80, "量化程度": 70}},
  "reason": "总体评分理由（50字内）",
  "passed": true
}}
passed=true表示score>=70分。只输出JSON。"""


class CriticAgent(BaseAgent):
    """
    Critic Agent — 给具体修改建议
    不是"降低风险"，而是"第3条经历增加处理QPS的具体数字"
    """

    name = "critic"
    description = "给出具体可执行的修改建议"

    def __init__(self):
        self._llm = get_llm_client()
        self._cost = CostMonitor.get_instance()

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        task_type = kwargs.get("task_type", "resume_optimize")
        original = kwargs.get("original", {})
        optimized = kwargs.get("optimized", {})
        judge_result = kwargs.get("judge_result", {})
        low_dimensions = kwargs.get("low_dimensions", [])

        if not low_dimensions and judge_result:
            # 从 judge 结果中提取低分维度
            dims = judge_result.get("dimensions", {})
            low_dimensions = [k for k, v in dims.items() if v < 70]

        prompt = f"""你是资深简历优化评审。针对以下低分维度给出**具体可执行**的修改建议。

# 低分维度
{json.dumps(low_dimensions, ensure_ascii=False)}

# 原始内容
{json.dumps(original, ensure_ascii=False, indent=2)[:800]}

# 优化后内容
{json.dumps(optimized, ensure_ascii=False, indent=2)[:800]}

# 要求
- 每条建议必须具体（如"第2条经历的highlights增加日均处理QPS数字"）
- 不要笼统说"提高量化程度"
- 每条建议15-30字
- 输出3-5条

# 输出格式
{{"suggestions": ["建议1", "建议2", "建议3"]}}"""

        response = self._llm.json(prompt)
        self._cost.record(
            task="critic", model=response.model,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            duration_ms=response.duration_ms, cost_usd=response.cost_usd,
        )

        try:
            result = json.loads(response.content)
        except json.JSONDecodeError:
            return AgentResult.fail("Critic JSON 无效")

        return AgentResult.ok(result, tokens=response.total_tokens)

    def critique_optimize(self, ctx: WorkflowContext, original: dict, optimized: dict,
                          dimensions: list[str] | None = None) -> AgentResult:
        """便捷方法：针对简历优化做批评"""
        if dimensions is None:
            dimensions = ["关键词匹配", "量化程度", "真实性保持", "针对性"]
        return self.run(ctx, task_type="resume_optimize", original=original,
                        optimized=optimized, low_dimensions=dimensions)
