"""
RetryPolicy — 指数退避 + 熔断器
Token/Cost Monitor — 统计 token、耗时、成本
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from loguru import logger

from src.exceptions import CircuitBreakerError, MaxRetryExceededError


@dataclass
class RetryPolicy:
    """指数退避重试策略"""

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)

    # 熔断器
    circuit_breaker_threshold: int = 5       # 连续失败 N 次打开熔断
    circuit_breaker_recovery_seconds: float = 30.0  # 熔断恢复时间

    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _circuit_open: bool = field(default=False, init=False)

    def _check_circuit(self) -> None:
        if not self._circuit_open:
            return
        if time.monotonic() - self._last_failure_time > self.circuit_breaker_recovery_seconds:
            self._circuit_open = False
            self._failure_count = 0
            logger.info("熔断器恢复，重新允许请求")
        else:
            raise CircuitBreakerError(f"熔断器开启中，{self.circuit_breaker_recovery_seconds}s 后恢复")

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.circuit_breaker_threshold:
            self._circuit_open = True
            logger.warning(f"连续失败 {self._failure_count} 次，熔断器打开")

    def _record_success(self) -> None:
        self._failure_count = 0

    def execute(self, fn: Callable, *args, **kwargs):
        """同步执行，自动重试"""
        self._check_circuit()

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                self._record_success()
                return result
            except self.retryable_exceptions as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(
                        self.base_delay_seconds * (self.backoff_multiplier ** attempt),
                        self.max_delay_seconds,
                    )
                    logger.warning(f"第 {attempt + 1} 次重试，{delay:.1f}s 后重试: {e}")
                    time.sleep(delay)
                else:
                    self._record_failure()

        raise MaxRetryExceededError(f"超过最大重试次数 {self.max_retries}: {last_error}")

    async def execute_async(self, fn: Callable, *args, **kwargs):
        """异步执行，自动重试"""
        self._check_circuit()

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await fn(*args, **kwargs)
                self._record_success()
                return result
            except self.retryable_exceptions as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(
                        self.base_delay_seconds * (self.backoff_multiplier ** attempt),
                        self.max_delay_seconds,
                    )
                    logger.warning(f"第 {attempt + 1} 次重试，{delay:.1f}s 后重试: {e}")
                    await asyncio.sleep(delay)
                else:
                    self._record_failure()

        raise MaxRetryExceededError(f"超过最大重试次数 {self.max_retries}: {last_error}")


@dataclass
class CostRecord:
    """单次调用成本记录"""
    task: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: float = 0.0
    cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.monotonic)


class CostMonitor:
    """Token / 耗时 / 成本统计器，单例"""

    _instance: "CostMonitor | None" = None

    def __init__(self):
        self._records: list[CostRecord] = []
        self._task_stats: dict[str, dict] = defaultdict(lambda: {
            "calls": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_duration_ms": 0.0,
        })

    @classmethod
    def get_instance(cls) -> "CostMonitor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record(self, task: str, model: str, prompt_tokens: int, completion_tokens: int,
               duration_ms: float, cost_usd: float) -> None:
        rec = CostRecord(
            task=task, model=model,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            duration_ms=duration_ms, cost_usd=cost_usd,
        )
        self._records.append(rec)

        stats = self._task_stats[task]
        stats["calls"] += 1
        stats["total_tokens"] += prompt_tokens + completion_tokens
        stats["total_cost"] += cost_usd
        stats["total_duration_ms"] += duration_ms

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self._records)

    @property
    def total_tokens(self) -> int:
        return sum(r.prompt_tokens + r.completion_tokens for r in self._records)

    @property
    def total_calls(self) -> int:
        return len(self._records)

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "Token / 成本统计",
            "=" * 50,
            f"总调用次数: {self.total_calls}",
            f"总 Token:   {self.total_tokens:,}",
            f"总成本:     ${self.total_cost:.4f} USD",
            "",
            "按任务统计:",
        ]
        for task, stats in sorted(self._task_stats.items()):
            lines.append(
                f"  {task:30s}  calls={stats['calls']:3d}  "
                f"tokens={stats['total_tokens']:6,d}  "
                f"cost=${stats['total_cost']:.4f}"
            )
        lines.append("=" * 50)
        return "\n".join(lines)

    def reset(self) -> None:
        self._records.clear()
        self._task_stats.clear()
