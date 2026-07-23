"""
Workflow Orchestrator — DAG 编排 + 断点恢复
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from src.repository.store import WorkflowRepository
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class WorkflowOrchestrator:
    """工作流编排器"""

    def __init__(self):
        self._repo = WorkflowRepository()

    def run_sequence(
        self, ctx: WorkflowContext, agents: list[BaseAgent], **shared_kwargs: Any
    ) -> list[AgentResult]:
        """串行执行 Agent 列表"""
        results = []
        current_ctx = ctx

        for agent in agents:
            logger.info(f"执行 Agent: {agent.name}")
            result = agent.run(current_ctx, **shared_kwargs)

            if not result.success:
                logger.error(f"Agent {agent.name} 执行失败: {result.error}，工作流中断")
                results.append(result)
                break

            results.append(result)
            current_ctx = current_ctx.replace(
                current_step=agent.name,
                extra={**current_ctx.extra, f"{agent.name}_result": result.data},
            )

        return results

    async def run_parallel(
        self, ctx: WorkflowContext, agents: list[BaseAgent], **shared_kwargs: Any
    ) -> list[AgentResult]:
        """并行执行 Agent 列表（适用于多平台搜索、多简历优化）"""
        async def run_one(agent: BaseAgent) -> AgentResult:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.run, ctx, **shared_kwargs)

        tasks = [run_one(a) for a in agents]
        return await asyncio.gather(*tasks)

    def save_state(self, ctx: WorkflowContext, results: dict[str, Any]) -> None:
        """持久化工作流状态（断点恢复用）"""
        state = {
            "session_id": ctx.session_id,
            "current_step": ctx.current_step,
            "selected_directions": ctx.selected_directions,
            "selected_jobs": ctx.selected_jobs,
            "results": {k: str(v)[:500] for k, v in results.items()},  # 截断存储
            "timestamp": time.time(),
        }
        self._repo.save(ctx.session_id, state)
        logger.info(f"工作流状态已保存: {ctx.session_id}")

    def load_state(self, session_id: str) -> dict[str, Any] | None:
        """加载工作流状态"""
        return self._repo.load(session_id)

    def can_resume(self, session_id: str) -> bool:
        return self._repo.exists(session_id)
