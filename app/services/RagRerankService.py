from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RagRerankCandidate:
    text: str
    payload: Any
    retrieval_score: float | None = None


class RagRerankService:
    def __init__(
        self,
        *,
        api_key: str,
        embedding_model: str,
        embed_dim: int,
        embedding_batch_size: int | None = None,
    ) -> None:
        batch_size = embedding_batch_size
        if batch_size is None:
            batch_size = 1 if embedding_model.strip().endswith("embedding-2") else 10
        self._embed_model = GoogleGenAIEmbedding(
            model_name=embedding_model,
            api_key=api_key,
            embedding_config={"output_dimensionality": embed_dim},
            embed_batch_size=max(1, batch_size),
        )

    async def rerank(
        self,
        query: str,
        candidates: list[RagRerankCandidate],
        *,
        top_n: int,
    ) -> list[tuple[float, RagRerankCandidate]]:
        if not candidates:
            return []
        if top_n < 1:
            return []

        query_text = query.strip()
        if not query_text:
            return [(c.retrieval_score or 0.0, c) for c in candidates[:top_n]]

        texts = [c.text.strip() or " " for c in candidates]
        all_texts = [query_text, *texts]
        try:
            embeddings = await self._embed_model.aget_text_embedding_batch(all_texts)
        except Exception as exc:
            logger.warning("aget_text_embedding_batch failed, falling back to concurrent one-by-one: %s", exc)
            embeddings = await asyncio.gather(*(self._embed_model.aget_text_embedding(t) for t in all_texts))

        scores = _batch_cosine_similarities(embeddings[0], embeddings[1:])
        scored: list[tuple[float, RagRerankCandidate]] = []
        for idx, candidate in enumerate(candidates):
            score = scores[idx] if idx < len(scores) else (candidate.retrieval_score or 0.0)
            scored.append((score, candidate))
        scored.sort(key=lambda row: row[0], reverse=True)
        return scored[:top_n]


def _batch_cosine_similarities(
    query_vec: list[float],
    doc_vecs: list[list[float]],
) -> list[float]:
    """query 벡터와 doc 벡터 목록의 코사인 유사도를 한 번의 행렬 연산으로 계산."""
    if not doc_vecs:
        return []
    q = np.asarray(query_vec, dtype=np.float64)
    docs = np.asarray(doc_vecs, dtype=np.float64)
    q_norm = float(np.linalg.norm(q))
    if q_norm == 0.0:
        return [0.0] * len(doc_vecs)
    doc_norms = np.linalg.norm(docs, axis=1)
    doc_norms = np.where(doc_norms == 0.0, 1.0, doc_norms)
    similarities = docs @ q / (doc_norms * q_norm)
    return np.clip(similarities, 0.0, 1.0).tolist()
