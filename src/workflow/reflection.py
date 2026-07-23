"""
Reflection Workflow — 闭环反馈机制
Agent 输出 → Reviewer 审核 → 不通过 → 回退重试 → 直到达标
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.agents.optimize_agent import QAAgent, ResumeOptimizeAgent
from src.models.schemas import JobDescription, OptimizedResume, UserProfile
from src.repository.store import ProfileRepository
from src.workflow.context import AgentResult, WorkflowContext


class ReflectionWorkflow:
    """带反思回路的优化工作流 — QA 不通过自动重优化"""

    def __init__(self, max_iterations: int = 3, target_risk: str = "low"):
        """
        Args:
            max_iterations: 最大优化迭代次数
            target_risk: 目标风险等级 (low/medium)
        """
        self._max_iterations = max_iterations
        self._target_risk = target_risk
        self._optimize_agent = ResumeOptimizeAgent()
        self._qa_agent = QAAgent()
        self._profile_repo = ProfileRepository()

    def optimize_with_reflection(
        self,
        profile_name: str,
        job: JobDescription,
        ctx: WorkflowContext | None = None,
    ) -> AgentResult:
        """
        带反思的简历优化：优化 → QA → 不通过→回退→重新优化
        最多迭代 max_iterations 次
        """
        ctx = ctx or WorkflowContext()
        profile_data = self._profile_repo.load(profile_name)
        if not profile_data:
            return AgentResult.fail(f"画像不存在: {profile_name}")

        profile = UserProfile(**profile_data)

        best_resume: OptimizedResume | None = None
        best_risk = "high"
        history: list[dict] = []  # 记录每次迭代

        for iteration in range(1, self._max_iterations + 1):
            logger.info(f"Reflection 迭代 {iteration}/{self._max_iterations}: {job.title} @ {job.company}")

            # 1) 优化
            opt_result = self._optimize_agent.run(
                ctx, profile_name=profile_name, job=job,
                iteration=iteration,
                previous_issues=history[-1].get("issues", []) if history else [],
            )
            if not opt_result.success:
                logger.error(f"优化失败 (iter {iteration}): {opt_result.error}")
                continue

            resume: OptimizedResume = opt_result.data

            # 2) QA 审核
            qa_result = self._qa_agent.run(
                ctx, original_profile=profile, optimized_resume=resume
            )
            if qa_result.success and qa_result.data:
                resume = qa_result.data

            risk = resume.qa_risk_level
            issues = resume.qa_warnings
            tokens = opt_result.tokens + (qa_result.tokens or 0)

            history.append({
                "iteration": iteration,
                "risk": risk,
                "issues": issues,
                "tokens": tokens,
            })

            # 追踪最佳结果
            risk_order = {"low": 0, "medium": 1, "high": 2}
            if risk_order.get(risk, 3) <= risk_order.get(best_risk, 3):
                best_resume = resume
                best_risk = risk

            # 3) 检查是否达标
            if self._is_acceptable(risk):
                logger.info(f"✅ Reflection 达标 (iter {iteration}): risk={risk}")
                return AgentResult.ok(
                    best_resume,
                    tokens=sum(h["tokens"] for h in history),
                    extra={"iterations": iteration, "history": history},
                )

            # 4) 未达标 → 记录问题 → 下一轮
            logger.warning(f"Reflection 未达标 (iter {iteration}): risk={risk}, issues={issues}")

        # 超出最大迭代 → 返回最佳结果 + 警告
        logger.warning(f"Reflection 达到最大迭代 ({self._max_iterations})，返回最佳结果: risk={best_risk}")
        return AgentResult.ok(
            best_resume,
            warnings=[f"经{self._max_iterations}轮优化，最终风险: {best_risk}"],
            tokens=sum(h["tokens"] for h in history),
            extra={"iterations": self._max_iterations, "history": history, "forced": True},
        )

    def _is_acceptable(self, risk: str) -> bool:
        """判断风险等级是否达标"""
        if self._target_risk == "low":
            return risk == "low"
        if self._target_risk == "medium":
            return risk in ("low", "medium")
        return True  # target=high 时任何结果都接受
