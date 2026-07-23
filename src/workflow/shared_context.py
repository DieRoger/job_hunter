"""
SharedContext — V3.2.1 统一上下文
所有 Agent 只读/写此对象，消灭 kwargs 散落
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.models.schemas import (
    CareerDirection,
    JobDescription,
    MatchResult,
    OptimizedResume,
    UserProfile,
)


@dataclass
class SharedContext:
    """
    全局共享上下文 — 所有 Agent 的单一数据源
    模式：Agent 读取需要的字段 → 执行 → 写回结果
    """

    # ─── 会话标识 ────────────────────────────────────
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str = "default"
    started_at: float = field(default_factory=time.time)

    # ─── 用户数据 ────────────────────────────────────
    profile: Optional[UserProfile] = None
    resume_text: str = ""                          # 原始简历文本
    profile_name: str = "default"                  # 画像名称

    # ─── 方向 + 搜索 ────────────────────────────────
    career_directions: List[CareerDirection] = field(default_factory=list)
    selected_direction_indices: List[int] = field(default_factory=list)

    raw_jobs: List[JobDescription] = field(default_factory=list)    # 爬虫原始数据
    analyzed_jobs: List[JobDescription] = field(default_factory=list)  # JD分析后
    match_results: List[MatchResult] = field(default_factory=list)     # 匹配评分后

    # ─── 优化结果 ────────────────────────────────────
    optimized_resume: Optional[OptimizedResume] = None
    greeting_message: str = ""
    qa_risk_level: str = "low"
    qa_warnings: List[str] = field(default_factory=list)
    ats_score: float = 0.0
    ats_details: Dict[str, Any] = field(default_factory=dict)

    # ─── 审核反馈 ────────────────────────────────────
    review_passed: bool = True
    review_comments: List[str] = field(default_factory=list)
    judge_score: float = 0.0
    critic_suggestions: List[str] = field(default_factory=list)

    # ─── 导出 ────────────────────────────────────────
    export_path: str = ""
    export_template: str = "professional"

    # ─── 元数据 ──────────────────────────────────────
    current_step: str = ""
    errors: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    # ─── 便捷方法 ────────────────────────────────────

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at

    def has_profile(self) -> bool:
        return self.profile is not None

    def has_jobs(self) -> bool:
        return len(self.analyzed_jobs) > 0 or len(self.raw_jobs) > 0

    def top_job(self) -> Optional[JobDescription]:
        """获取评分最高的职位"""
        if self.match_results:
            return self.match_results[0].job
        if self.analyzed_jobs:
            return self.analyzed_jobs[0]
        if self.raw_jobs:
            return self.raw_jobs[0]
        return None

    def top_career(self) -> Optional[CareerDirection]:
        if self.career_directions:
            return self.career_directions[0]
        return None

    def record_error(self, error: str) -> None:
        self.errors.append(f"[{self.current_step}] {error}")

    def summary(self) -> dict:
        """上下文摘要"""
        return {
            "session": self.session_id,
            "user": self.user_id,
            "step": self.current_step,
            "has_profile": self.has_profile(),
            "has_jobs": self.has_jobs(),
            "career_count": len(self.career_directions),
            "job_count": len(self.analyzed_jobs) or len(self.raw_jobs),
            "match_count": len(self.match_results),
            "optimized": self.optimized_resume is not None,
            "qa_risk": self.qa_risk_level,
            "ats_score": self.ats_score,
            "errors": len(self.errors),
            "elapsed": f"{self.elapsed_seconds:.1f}s",
        }
