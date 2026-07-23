"""
LLM 抽象层 — 统一接口，基于 httpx 直接调用 API（兼容 Python 3.7+）
业务层永远通过 LLMClient.generate() / chat() / json() 调用
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.config import model_config
from src.exceptions import (
    LLMAuthError,
    LLMContextOverflowError,
    LLMError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
)


@dataclass
class LLMResponse:
    """LLM 统一返回结构"""
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0.0
    raw: Any = None

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0) or (
            self.usage.get("prompt_tokens", 0) + self.usage.get("completion_tokens", 0)
        )

    @property
    def cost_usd(self) -> float:
        info = _model_cost_info.get(self.model, _model_cost_info.get("deepseek-chat", {}))
        prompt_cost = self.usage.get("prompt_tokens", 0) / 1000 * info.get("input", 0)
        completion_cost = self.usage.get("completion_tokens", 0) / 1000 * info.get("output", 0)
        return prompt_cost + completion_cost


_model_cost_info: dict[str, dict[str, float]] = {
    "deepseek-chat":     {"input": 0.00014, "output": 0.00028},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    "deepseek-v4-flash": {"input": 0.00014, "output": 0.00028},
    "gpt-4o":            {"input": 0.00250, "output": 0.01000},
    "gpt-4o-mini":       {"input": 0.00015, "output": 0.00060},
}


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类"""
    provider: str = "unknown"

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse: ...
    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse: ...
    @abstractmethod
    def json(self, prompt: str, schema: dict[str, Any] | None = None, **kwargs: Any) -> LLMResponse: ...
    @abstractmethod
    def stream(self, prompt: str, **kwargs: Any) -> Any: ...


class HttpxLLMClient(BaseLLMClient):
    """基于 httpx 的 LLM 客户端基类 — 不依赖 openai SDK"""

    provider = "httpx"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or ""
        self.base_url = base_url or ""
        self.default_model = "deepseek-chat"
        self.reasoner_model = "deepseek-reasoner"
        self._client = httpx.Client(timeout=60.0, proxies={})

    def _call(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        model = model or self.default_model
        start = time.perf_counter()

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            body["response_format"] = response_format

        try:
            resp = self._client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=kwargs.get("request_timeout", 60),
            )
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(str(e)) from e
        except Exception as e:
            raise LLMError(str(e)) from e

        if resp.status_code == 401:
            raise LLMAuthError("API Key 无效或过期")
        if resp.status_code == 429:
            raise LLMRateLimitError("请求频率超限")
        if resp.status_code >= 500:
            raise LLMError(f"服务器错误: {resp.status_code}")

        if resp.status_code != 200:
            raise LLMError(f"API 错误 ({resp.status_code}): {resp.text[:500]}")

        data = resp.json()
        duration_ms = (time.perf_counter() - start) * 1000

        choices = data.get("choices", [])
        content = ""
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "") or ""

        usage_data = data.get("usage", {})
        usage = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

        return LLMResponse(
            content=content,
            model=data.get("model", model),
            usage=usage,
            duration_ms=duration_ms,
            raw=data,
        )

    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return self._call([{"role": "user", "content": prompt}], **kwargs)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        return self._call(messages, **kwargs)

    def json(self, prompt: str, schema: dict[str, Any] | None = None, **kwargs: Any) -> LLMResponse:
        system_msg = "你必须始终以有效的 JSON 格式回答，不要包含任何其他内容。"
        if schema:
            system_msg += "\nJSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
        return self._call(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            **kwargs,
        )

    def stream(self, prompt: str, **kwargs: Any) -> Any:
        raise NotImplementedError("流式暂不支持，请使用 generate()")


class DeepSeekClient(HttpxLLMClient):
    """DeepSeek API 客户端"""

    provider = "deepseek"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            raise LLMAuthError("DEEPSEEK_API_KEY 未设置")

        provider_cfg = model_config.providers.get("deepseek")
        self.base_url = base_url or (provider_cfg.base_url if provider_cfg else "https://api.deepseek.com/v1")
        self.default_model = (provider_cfg.default_model if provider_cfg else "deepseek-chat")
        self.reasoner_model = (provider_cfg.reasoner_model if provider_cfg else "deepseek-reasoner")
        self._client = httpx.Client(timeout=60.0, proxies={})


class OpenAIClient(HttpxLLMClient):
    """OpenAI API 客户端"""
    provider = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not self.api_key:
            raise LLMAuthError("OPENAI_API_KEY 未设置")
        self.base_url = base_url or "https://api.openai.com/v1"
        self.default_model = "gpt-4o-mini"
        self._client = httpx.Client(timeout=60.0, proxies={})


_provider_registry: dict[str, type[BaseLLMClient]] = {
    "deepseek": DeepSeekClient,
    "openai": OpenAIClient,
}


def get_llm_client(provider: str | None = None, **kwargs: Any) -> BaseLLMClient:
    if provider is None:
        provider = "deepseek"
    client_cls = _provider_registry.get(provider)
    if client_cls is None:
        raise LLMError(f"不支持的 LLM provider: {provider}，可用: {list(_provider_registry)}")
    return client_cls(**kwargs)
