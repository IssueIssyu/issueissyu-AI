from __future__ import annotations

from typing import Any

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

from app.services.internal.ai.gemini_key_pool import GeminiKeyPool


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

    def _embed_model_at(self, index: int) -> GoogleGenAIEmbedding:
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

    def _get_text_embedding(self, text: str) -> list[float]:
        idx, _, _ = self._key_pool.acquire_sync()
        return self._embed_model_at(idx).get_text_embedding(text)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        idx, _, _ = await self._key_pool.acquire()
        return await self._embed_model_at(idx).aget_text_embedding(text)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        idx, _, _ = self._key_pool.acquire_sync()
        return self._embed_model_at(idx).get_text_embedding_batch(texts)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        idx, _, _ = await self._key_pool.acquire()
        return await self._embed_model_at(idx).aget_text_embedding_batch(texts)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._get_text_embedding(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await self._aget_text_embedding(query)

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
