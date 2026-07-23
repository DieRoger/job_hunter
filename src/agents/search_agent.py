"""
Search Agent — 多平台职位搜索
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from src.models.schemas import JobDescription
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext


class BasePlatformAdapter(ABC):
    """招聘平台适配器抽象基类"""

    platform: str = "unknown"

    @abstractmethod
    async def search(self, keyword: str, city: str = "北京", top_n: int = 10) -> list[JobDescription]:
        """搜索职位"""
        ...

    @abstractmethod
    async def parse_job(self, job_id: str) -> JobDescription:
        """解析单个职位详情"""
        ...

    async def login(self) -> bool:
        """登录（可选，部分平台需要）"""
        return True

    async def apply(self, job_id: str, resume_path: str, greeting: str) -> bool:
        """投递简历（阶段二）"""
        raise NotImplementedError


class SearchAgent(BaseAgent):
    """职位搜索 Agent"""

    name = "search_agent"
    description = "在招聘平台搜索职位并标准化"

    def __init__(self):
        self._adapters: dict[str, BasePlatformAdapter] = {}

    def register_adapter(self, platform: str, adapter: BasePlatformAdapter) -> None:
        self._adapters[platform] = adapter
        logger.info(f"注册平台适配器: {platform}")

    async def execute_async(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        """异步搜索多平台"""
        keyword = kwargs.get("keyword", "")
        city = kwargs.get("city", "北京")
        platforms = kwargs.get("platforms", list(self._adapters.keys()))
        top_n = kwargs.get("top_n", 10)

        if not keyword:
            return AgentResult.fail("未提供搜索关键词")

        all_jobs: list[JobDescription] = []
        for platform in platforms:
            adapter = self._adapters.get(platform)
            if not adapter:
                logger.warning(f"平台适配器未注册: {platform}")
                continue
            try:
                jobs = await adapter.search(keyword=keyword, city=city, top_n=top_n)
                all_jobs.extend(jobs)
                logger.info(f"{platform} 搜索到 {len(jobs)} 个职位")
            except Exception as e:
                logger.error(f"{platform} 搜索失败: {e}")

        return AgentResult.ok(all_jobs, extra={"keyword": keyword, "total": len(all_jobs)})

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        """同步入口 — 实际搜索请用 execute_async"""
        import asyncio
        return asyncio.run(self.execute_async(ctx, **kwargs))
