"""
Memory 系统 — V3.1 核心升级
User Memory 持久化 + 跨会话复用 + 历史轨迹 + 偏好学习
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.models.schemas import UserProfile


@dataclass
class MemoryEntry:
    """单条记忆"""
    key: str
    value: Any
    timestamp: float = field(default_factory=time.time)
    ttl: float | None = None  # 过期时间（秒），None=永不过期
    access_count: int = 0
    tags: list[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl


@dataclass
class SessionRecord:
    """单次会话记录"""
    session_id: str
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    actions: list[dict] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)


class UserMemory:
    """
    用户记忆系统
    - 跨会话持久化
    - 自动加载/保存
    - 访问频率跟踪
    - TTL过期机制
    """

    def __init__(self, user_id: str = "default", data_dir: str | Path | None = None):
        self.user_id = user_id
        if data_dir is None:
            data_dir = Path.home() / ".job-hunter" / "memory"
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._memory_path = self._data_dir / f"{user_id}.json"

        # 记忆存储
        self._profile: UserProfile | None = None
        self._skills: dict[str, dict] = {}        # 技能→{level, years, last_used}
        self._experiences: list[dict] = []         # 工作经历
        self._preferences: dict[str, Any] = {}     # 偏好（城市/薪资/行业）
        self._history: list[SessionRecord] = []    # 历史会话
        self._applied_jobs: list[dict] = []        # 已投递
        self._favorite_jobs: list[dict] = []       # 收藏
        self._interviews: list[dict] = []          # 面试记录
        self._offers: list[dict] = []              # Offer记录
        self._learning_progress: dict[str, Any] = {}  # 学习进度

        self._load()

    # ─── 持久化 ──────────────────────────────────────────

    def _load(self) -> None:
        if not self._memory_path.exists():
            return
        try:
            data = json.loads(self._memory_path.read_text(encoding="utf-8"))
            self._profile = UserProfile(**data["profile"]) if data.get("profile") else None
            self._skills = data.get("skills", {})
            self._experiences = data.get("experiences", [])
            self._preferences = data.get("preferences", {})
            self._applied_jobs = data.get("applied_jobs", [])
            self._favorite_jobs = data.get("favorite_jobs", [])
            self._interviews = data.get("interviews", [])
            self._offers = data.get("offers", [])
            self._learning_progress = data.get("learning_progress", {})
            # 历史会话不持久化完整记录，只保留摘要
            logger.info(f"Memory 加载完成: {self.user_id} ({len(self._skills)}技能, {len(self._applied_jobs)}投递)")
        except Exception as e:
            logger.warning(f"Memory 加载失败: {e}")

    def save(self) -> None:
        data = {
            "profile": self._profile.model_dump() if self._profile else None,
            "skills": self._skills,
            "experiences": self._experiences,
            "preferences": self._preferences,
            "applied_jobs": self._applied_jobs[-50:],   # 保留最近50条
            "favorite_jobs": self._favorite_jobs[-50:],
            "interviews": self._interviews[-30:],
            "offers": self._offers[-20:],
            "learning_progress": self._learning_progress,
            "updated_at": time.time(),
        }
        self._memory_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug(f"Memory 已保存: {self.user_id}")

    # ─── Profile ─────────────────────────────────────────

    @property
    def profile(self) -> UserProfile | None:
        return self._profile

    @profile.setter
    def profile(self, value: UserProfile) -> None:
        self._profile = value
        # 自动同步技能
        for skill in value.skills:
            self._skills[skill.name] = {
                "level": skill.level,
                "years": skill.years,
                "category": skill.category,
                "last_used": time.time(),
            }
        self.save()

    def update_skill(self, name: str, level: str = "", years: float = 0.0) -> None:
        if name in self._skills:
            if level:
                self._skills[name]["level"] = level
            if years:
                self._skills[name]["years"] = years
            self._skills[name]["last_used"] = time.time()
        else:
            self._skills[name] = {"level": level, "years": years, "category": "", "last_used": time.time()}
        self.save()

    # ─── Preferences ─────────────────────────────────────

    def set_preference(self, key: str, value: Any) -> None:
        self._preferences[key] = value
        self.save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._preferences.get(key, default)

    # ─── Job Tracking ────────────────────────────────────

    def record_apply(self, job_id: str, company: str, title: str, status: str = "applied") -> None:
        self._applied_jobs.append({
            "job_id": job_id,
            "company": company,
            "title": title,
            "status": status,
            "applied_at": time.time(),
        })
        self.save()

    def record_interview(self, job_id: str, company: str, title: str, stage: str, notes: str = "") -> None:
        self._interviews.append({
            "job_id": job_id,
            "company": company,
            "title": title,
            "stage": stage,
            "notes": notes,
            "at": time.time(),
        })
        # 更新投递状态
        for job in self._applied_jobs:
            if job["job_id"] == job_id:
                job["status"] = f"interview_{stage}"
        self.save()

    def record_offer(self, job_id: str, company: str, title: str, salary: str, accepted: bool = False) -> None:
        self._offers.append({
            "job_id": job_id,
            "company": company,
            "title": title,
            "salary": salary,
            "accepted": accepted,
            "at": time.time(),
        })
        for job in self._applied_jobs:
            if job["job_id"] == job_id:
                job["status"] = "offered"
        self.save()

    def add_favorite(self, job_id: str, company: str, title: str) -> None:
        self._favorite_jobs.append({
            "job_id": job_id,
            "company": company,
            "title": title,
            "favorited_at": time.time(),
        })
        self.save()

    # ─── Learning Progress ───────────────────────────────

    def update_learning(self, skill: str, progress: float) -> None:
        """更新学习进度 (0-100)"""
        self._learning_progress[skill] = {
            "progress": progress,
            "updated_at": time.time(),
        }
        self.save()

    # ─── Analytics ────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """统计分析"""
        total_applied = len(self._applied_jobs)
        interviews = len(self._interviews)
        offers = len(self._offers)
        return {
            "total_applied": total_applied,
            "interviews": interviews,
            "interview_rate": f"{interviews / total_applied * 100:.1f}%" if total_applied else "N/A",
            "offers": offers,
            "offer_rate": f"{offers / total_applied * 100:.1f}%" if total_applied else "N/A",
            "skills_count": len(self._skills),
            "favorites": len(self._favorite_jobs),
        }

    @property
    def skill_summary(self) -> str:
        """技能摘要"""
        lines = []
        for name, info in sorted(self._skills.items(), key=lambda x: -x[1].get("years", 0)):
            lines.append(f"  {name}: {info.get('level','?')} ({info.get('years',0)}年)")
        return "\n".join(lines) if lines else "无技能记录"
