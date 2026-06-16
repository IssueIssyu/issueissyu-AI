from __future__ import annotations

import threading
from typing import Any

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

from app.services.internal.ai.gemini_key_pool import GeminiKeyPool
from app.services.internal.ai.gemini_retry import is_retryable_gemini_error


class RotatingGoogleGenAIEmbedding(BaseEmbedding):
    """GeminiKeyPool round-robin으로 GoogleGenAIEmbedding 호출을 분산."""

    def __init__(
        self,
        *,
        key_pool: GeminiKeyPool,
        model_name: str,
        embed_dim: int,
        embed_batch_size: int,
    ) -> None:
        super().__init__(
            model_name=model_name,
            embed_batch_size=max(1, embed_batch_size),
        )
        self._key_pool = key_pool
        self._embed_dim = embed_dim
        self._embed_batch_size = max(1, embed_batch_size)
        self._models_by_index: dict[int, GoogleGenAIEmbedding] = {}
        self._lock = threading.Lock()

    def _embed_model_at(self, index: int) -> GoogleGenAIEmbedding:
        with self._lock:
            model = self._models_by_index.get(index)
            if model is None:
                model = GoogleGenAIEmbedding(
                    model_name=self.model_name,
                    api_key=self._key_pool.api_key_at(index),
                    embedding_config={"output_dimensionality": self._embed_dim},
                    embed_batch_size=self._embed_batch_size,
                )
                self._models_by_index[index] = model
            return model

    def _execute_with_failover(self, func_name: str, *args: Any, **kwargs: Any) -> Any:
        idx, _, _ = self._key_pool.acquire_sync()
        try:
            return getattr(self._embed_model_at(idx), func_name)(*args, **kwargs)
        except Exception as exc:
            if not is_retryable_gemini_error(exc):
                raise
            last_error: Exception | None = exc
            for failover_idx in self._key_pool.failover_indices(idx):
                try:
                    return getattr(self._embed_model_at(failover_idx), func_name)(*args, **kwargs)
                except Exception as failover_exc:
                    last_error = failover_exc
                    if not is_retryable_gemini_error(failover_exc):
                        raise
            if last_error is not None:
                raise last_error
            raise

    async def _aexecute_with_failover(self, func_name: str, *args: Any, **kwargs: Any) -> Any:
        idx, _, _ = await self._key_pool.acquire()
        try:
            return await getattr(self._embed_model_at(idx), func_name)(*args, **kwargs)
        except Exception as exc:
            if not is_retryable_gemini_error(exc):
                raise
            last_error: Exception | None = exc
            for failover_idx in self._key_pool.failover_indices(idx):
                try:
                    return await getattr(self._embed_model_at(failover_idx), func_name)(*args, **kwargs)
                except Exception as failover_exc:
                    last_error = failover_exc
                    if not is_retryable_gemini_error(failover_exc):
                        raise
            if last_error is not None:
                raise last_error
            raise

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._execute_with_failover("get_text_embedding", text)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return await self._aexecute_with_failover("aget_text_embedding", text)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._execute_with_failover("get_text_embedding_batch", texts)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return await self._aexecute_with_failover("aget_text_embedding_batch", texts)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._execute_with_failover("get_query_embedding", query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await self._aexecute_with_failover("aget_query_embedding", query)

    @classmethod
    def class_name(cls) -> str:
        return "RotatingGoogleGenAIEmbedding"

    def _get_text_embedding_safe(self, text: str) -> list[float]:
        return self._get_text_embedding(text)

    async def _aget_text_embedding_safe(self, text: str) -> list[float]:
        return await self._aget_text_embedding(text)

    def _get_text_embeddings_safe(self, texts: list[str]) -> list[list[float]]:
        return self._get_text_embeddings(texts)

    async def _aget_text_embeddings_safe(self, texts: list[str]) -> list[list[float]]:
        return await self._aget_text_embeddings(texts)

    def _get_query_embedding_safe(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_query_embedding_safe(self, query: str) -> list[float]:
        return await self._aget_query_embedding(query)
