"""
LLM Router + Embedding 抽象层（基于 httpx）
"""

from __future__ import annotations

import math
import os
import re

import httpx

from src.config import model_config
from src.llm.client import BaseLLMClient, DeepSeekClient, get_llm_client


class LLMRouter:
    """按任务类型路由到合适的模型"""

    def __init__(self, client: BaseLLMClient | None = None):
        self._client = client or get_llm_client()
        self._rules = model_config.router.rules if model_config.router else []

    def resolve_model(self, task: str) -> str:
        for rule in self._rules:
            if re.search(rule.task_pattern, task, re.IGNORECASE):
                if rule.model == "reasoner":
                    return self._get_reasoner_model()
                return self._get_default_model()
        return self._get_default_model()

    def _get_default_model(self) -> str:
        if isinstance(self._client, DeepSeekClient):
            return self._client.default_model
        return "deepseek-chat"

    def _get_reasoner_model(self) -> str:
        if isinstance(self._client, DeepSeekClient):
            return self._client.reasoner_model
        return "deepseek-reasoner"

    @property
    def client(self) -> BaseLLMClient:
        return self._client


class EmbeddingClient:
    """统一 Embedding 抽象层（基于 httpx）"""

    def __init__(self, provider: str | None = None, api_key: str | None = None):
        if provider is None:
            provider = model_config.router.embedding_provider if model_config.router else "deepseek"

        self.provider = provider
        self.model = model_config.router.embedding_model if model_config.router else "deepseek-embed"

        if provider == "deepseek":
            self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
            self.base_url = "https://api.deepseek.com/v1"
        elif provider == "openai":
            self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
            self.base_url = "https://api.openai.com/v1"
        else:
            raise ValueError(f"不支持的 Embedding provider: {provider}")

        self._client = httpx.Client(timeout=30.0, proxies={})

    def embed(self, text: str) -> list[float]:
        """单文本嵌入"""
        resp = self._client.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": text},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Embedding 失败 ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        return data["data"][0]["embedding"] if data.get("data") else []

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入"""
        resp = self._client.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Embedding 批量失败 ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        return [d["embedding"] for d in data.get("data", [])]

    def similarity(self, a: list[float], b: list[float]) -> float:
        """余弦相似度"""
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
