"""
WorkflowContext — 不可变上下文快照，贯穿工作流生命周期
BaseAgent — 统一 Agent 生命周期：validate → execute → post_validate
AgentResult — 标准 Agent 返回结构
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from src.config import ConfigLoader

T = TypeVar("T")


@dataclass(frozen=True)
class WorkflowContext:
    """不可变工作流上下文 — 通过 replace() 创建新快照"""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str | None = None
    config: ConfigLoader = field(default_factory=ConfigLoader.get_instance)

    # 运行时状态
    current_step: str = ""
    selected_directions: list[int] = field(default_factory=list)
    selected_jobs: list[str] = field(default_factory=list)

    # 元数据
    started_at: float = field(default_factory=time.monotonic)
    extra: dict[str, Any] = field(default_factory=dict)

    def replace(self, **changes: Any) -> WorkflowContext:
        """返回新快照（不可变更新）"""
        current = {k: getattr(self, k) for k in self.__dataclass_fields__}  # type: ignore[attr-defined]
        current.update(changes)
        return WorkflowContext(**current)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at


@dataclass
class AgentResult(Generic[T]):
    """Agent 统一返回结构"""

    success: bool
    data: T | None = None
    error: str | None = None
    tokens: int = 0
    duration_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: T, **kwargs: Any) -> AgentResult[T]:
        return cls(success=True, data=data, **kwargs)

    @classmethod
    def fail(cls, error: str, **kwargs: Any) -> AgentResult[T]:
        return cls(success=False, error=error, **kwargs)


class BaseAgent:
    """Agent 基类 — 统一生命周期"""

    name: str = "base_agent"
    description: str = ""

    def validate(self, ctx: WorkflowContext) -> bool:
        """执行前校验，子类可覆盖"""
        return True

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        """核心执行逻辑，子类必须实现"""
        raise NotImplementedError

    def post_validate(self, result: AgentResult, ctx: WorkflowContext) -> AgentResult:
        """执行后校验，子类可覆盖"""
        return result

    def run(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        """统一入口：validate → execute → post_validate"""
        if not self.validate(ctx):
            return AgentResult.fail(f"{self.name}: 前置校验失败")

        start = time.perf_counter()
        result = self.execute(ctx, **kwargs)
        result.duration_ms = (time.perf_counter() - start) * 1000

        result = self.post_validate(result, ctx)
        return result
