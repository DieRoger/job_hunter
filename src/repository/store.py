"""
Repository Layer — 数据持久化抽象，Domain 和 Agent 不直接接触文件系统
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.exceptions import RepositoryError


class BaseRepository:
    """Repository 基类"""

    namespace: str = "default"

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            data_dir = Path.home() / ".job-hunter"
        self._data_dir = Path(data_dir) / self.namespace
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = key.replace("/", "-").replace("\\", "-").replace(":", "-").replace("*", "").replace("?", "").replace('"', "").replace("<", "").replace(">", "").replace("|", "")
        return self._data_dir / f"{safe_key}.json"

    def save(self, key: str, data: dict[str, Any]) -> None:
        path = self._path(key)
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            raise RepositoryError(f"保存失败 {self.namespace}/{key}: {e}") from e

    def load(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise RepositoryError(f"加载失败 {self.namespace}/{key}: {e}") from e

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def list_keys(self) -> list[str]:
        return [p.stem for p in self._data_dir.glob("*.json")]

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class ProfileRepository(BaseRepository):
    """用户画像存储"""
    namespace = "profiles"


class JobRepository(BaseRepository):
    """职位数据存储"""
    namespace = "jobs"


class ResumeRepository(BaseRepository):
    """简历数据存储"""
    namespace = "resumes"


class WorkflowRepository(BaseRepository):
    """工作流状态存储（断点恢复）"""
    namespace = "workflows"
