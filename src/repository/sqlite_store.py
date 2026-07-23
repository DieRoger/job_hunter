"""
SQLite Repository — V3.2.2
接口与 BaseRepository 完全一致，一行代码切换 JSON → SQLite
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.exceptions import RepositoryError


class SQLiteRepository:
    """SQLite 存储基类 — 与 BaseRepository 接口完全一致"""

    namespace: str = "default"

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".job-hunter" / "job_hunter.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.namespace} (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.commit()

    def save(self, key: str, data: Dict[str, Any]) -> None:
        try:
            self._conn.execute(f"""
                INSERT OR REPLACE INTO {self.namespace} (key, data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (key, json.dumps(data, ensure_ascii=False)))
            self._conn.commit()
        except sqlite3.Error as e:
            raise RepositoryError(f"SQLite保存失败 {self.namespace}/{key}: {e}") from e

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            row = self._conn.execute(
                f"SELECT data FROM {self.namespace} WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["data"])
        except (sqlite3.Error, json.JSONDecodeError) as e:
            raise RepositoryError(f"SQLite加载失败 {self.namespace}/{key}: {e}") from e

    def delete(self, key: str) -> None:
        self._conn.execute(f"DELETE FROM {self.namespace} WHERE key = ?", (key,))
        self._conn.commit()

    def list_keys(self) -> List[str]:
        rows = self._conn.execute(f"SELECT key FROM {self.namespace}").fetchall()
        return [r["key"] for r in rows]

    def exists(self, key: str) -> bool:
        row = self._conn.execute(
            f"SELECT 1 FROM {self.namespace} WHERE key = ?", (key,)
        ).fetchone()
        return row is not None

    def query(self, where: str = "", params: tuple = (),
              order_by: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """高级查询 — SQLite 特有优势"""
        sql = f"SELECT key, data, updated_at FROM {self.namespace}"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {limit}"
        rows = self._conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            data = json.loads(r["data"])
            data["_key"] = r["key"]
            data["_updated_at"] = r["updated_at"]
            results.append(data)
        return results

    def count(self, where: str = "", params: tuple = ()) -> int:
        sql = f"SELECT COUNT(*) FROM {self.namespace}"
        if where:
            sql += f" WHERE {where}"
        return self._conn.execute(sql, params).fetchone()[0]

    def close(self) -> None:
        self._conn.close()


class SQLiteProfileRepository(SQLiteRepository):
    namespace = "profiles"

class SQLiteJobRepository(SQLiteRepository):
    namespace = "jobs"

class SQLiteResumeRepository(SQLiteRepository):
    namespace = "resumes"

class SQLiteWorkflowRepository(SQLiteRepository):
    namespace = "workflows"

class SQLiteInterviewRepository(SQLiteRepository):
    namespace = "interviews"
