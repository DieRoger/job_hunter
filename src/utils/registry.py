"""
Prompt Registry — Prompt 模板注册 + JSON Schema 校验 + 渲染
Cache Manager — 统一缓存接口（JSON 文件，可切换 SQLite/Redis）
Plugin Manager — 插件注册发现
Event Bus — 发布订阅
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from src.exceptions import CacheError, ConfigurationError

# ─── Prompt Registry ──────────────────────────────────────

class PromptRegistry:
    """Prompt 模板注册中心 — Prompt 与 JSON Schema 绑定，加载时校验"""

    _instance: PromptRegistry | None = None
    _prompts_dir: Path = Path()  # placeholder, 在 __init__ 中被覆盖

    def __init__(self, prompts_dir: str | Path | None = None):
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent.parent / "prompts"
        self._prompts_dir = Path(prompts_dir)
        self._templates: dict[str, str] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        self._preload()

    @classmethod
    def get_instance(cls, prompts_dir: str | Path | None = None) -> PromptRegistry:
        if cls._instance is None:
            cls._instance = cls(prompts_dir)
        return cls._instance

    def _preload(self) -> None:
        """预加载所有 prompts/*.md"""
        if not self._prompts_dir.exists():
            logger.warning(f"Prompt 目录不存在: {self._prompts_dir}")
            return
        for md_file in self._prompts_dir.glob("*.md"):
            name = md_file.stem
            content = md_file.read_text(encoding="utf-8")
            self._templates[name] = content

            # 自动提取 JSON Schema（如果有 frontmatter）
            schema = self._extract_schema(content)
            if schema:
                self._schemas[name] = schema
            logger.debug(f"已加载 Prompt: {name} (schema={'✓' if schema else '✗'})")

    def _extract_schema(self, content: str) -> dict[str, Any] | None:
        """从 Markdown frontmatter 提取 JSON Schema"""
        match = re.search(r'```json\s*\n(.*?)\n```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        return None

    def register(self, name: str, template: str, schema: dict[str, Any] | None = None) -> None:
        """手动注册 Prompt"""
        self._templates[name] = template
        if schema:
            self._schemas[name] = schema

    def get(self, name: str) -> str:
        """获取原始模板"""
        if name not in self._templates:
            raise ConfigurationError(f"Prompt 未注册: {name}，可用: {list(self._templates.keys())}")
        return self._templates[name]

    def get_schema(self, name: str) -> dict[str, Any] | None:
        """获取绑定的 JSON Schema"""
        return self._schemas.get(name)

    def render(self, name: str, **variables: Any) -> str:
        """渲染模板（{{ variable }} 风格替换）"""
        template = self.get(name)

        def replace_var(m: re.Match) -> str:
            var_name = m.group(1).strip()
            if var_name in variables:
                val = variables[var_name]
                if isinstance(val, (list, dict)):
                    return json.dumps(val, ensure_ascii=False, indent=2)
                return str(val)
            return m.group(0)

        return re.sub(r'{{\s*(\w+)\s*}}', replace_var, template)

    @property
    def names(self) -> list[str]:
        return list(self._templates.keys())


# ─── Cache Manager ────────────────────────────────────────

class CacheManager:
    """统一缓存接口 — 默认 JSON 文件存储，可切换 SQLite/Redis"""

    def __init__(self, cache_dir: str | Path | None = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "cache"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def hash_key(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _path(self, namespace: str, key: str) -> Path:
        ns_dir = self._cache_dir / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        return ns_dir / f"{self.hash_key(key)}.json"

    def get(self, namespace: str, key: str) -> Any | None:
        """读取缓存"""
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise CacheError(f"缓存读取失败 {namespace}/{key}: {e}") from e

    def set(self, namespace: str, key: str, value: Any) -> None:
        """写入缓存"""
        path = self._path(namespace, key)
        try:
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            raise CacheError(f"缓存写入失败 {namespace}/{key}: {e}") from e

    def has(self, namespace: str, key: str) -> bool:
        return self._path(namespace, key).exists()

    def delete(self, namespace: str, key: str) -> None:
        path = self._path(namespace, key)
        if path.exists():
            path.unlink()

    def clear_namespace(self, namespace: str) -> None:
        ns_dir = self._cache_dir / namespace
        if ns_dir.exists():
            for f in ns_dir.glob("*.json"):
                f.unlink()


# ─── Plugin Manager ───────────────────────────────────────

class PluginManager:
    """插件注册与发现"""

    def __init__(self):
        self._plugins: dict[str, dict[str, Any]] = {}  # {platform: {adapter, ...}}

    def register(self, platform: str, name: str, plugin: Any) -> None:
        if platform not in self._plugins:
            self._plugins[platform] = {}
        self._plugins[platform][name] = plugin
        logger.info(f"插件已注册: {platform}/{name}")

    def get(self, platform: str, name: str) -> Any | None:
        return self._plugins.get(platform, {}).get(name)

    def list_platforms(self) -> list[str]:
        return list(self._plugins.keys())

    def list_plugins(self, platform: str) -> list[str]:
        return list(self._plugins.get(platform, {}).keys())


# ─── Event Bus ────────────────────────────────────────────

EventCallback = Callable[[str, dict[str, Any]], None]


class EventBus:
    """轻量事件总线 — 发布订阅"""

    def __init__(self):
        self._subscribers: dict[str, list[EventCallback]] = {}

    def subscribe(self, event: str, callback: EventCallback) -> None:
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(callback)

    def unsubscribe(self, event: str, callback: EventCallback) -> None:
        if event in self._subscribers:
            self._subscribers[event] = [cb for cb in self._subscribers[event] if cb is not callback]

    def publish(self, event: str, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        for callback in self._subscribers.get(event, []):
            try:
                callback(event, data)
            except Exception as e:
                logger.error(f"EventBus 回调异常 [{event}]: {e}")

    @property
    def events(self) -> list[str]:
        return list(self._subscribers.keys())
