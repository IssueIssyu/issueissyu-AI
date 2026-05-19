from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RagRerankCandidate:
    text: str
    payload: Any
    retrieval_score: float | None = None


class RagRerankService:
    # 쿼리, 문서 임베딩 코사인 유사도로 2차 정렬 (Gemini embedding)
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
        embeddings = await run_in_threadpool(
            self._embed_texts,
            [query_text, *texts],
        )
        if len(embeddings) != len(texts) + 1:
            logger.warning(
                "Rerank embedding count mismatch: expected %d, got %d",
                len(texts) + 1,
                len(embeddings),
            )
            embeddings = await run_in_threadpool(
                self._embed_texts_one_by_one,
                [query_text, *texts],
            )

        query_vec = embeddings[0]
        doc_vecs = embeddings[1:]
        scored: list[tuple[float, RagRerankCandidate]] = []
        for idx, candidate in enumerate(candidates):
            doc_vec = doc_vecs[idx] if idx < len(doc_vecs) else None
            if doc_vec is not None:
                score = _cosine_similarity(query_vec, doc_vec)
            else:
                score = candidate.retrieval_score or 0.0
            scored.append((score, candidate))
        scored.sort(key=lambda row: row[0], reverse=True)
        return scored[:top_n]

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._embed_model.get_text_embedding_batch(texts)
        if len(vectors) == len(texts):
            return vectors
        logger.warning(
            "get_text_embedding_batch가 %d/%d 개의 벡터만 반환해서, 하나씩 처리하는 방식으로 전환",
            len(vectors),
            len(texts),
        )
        return self._embed_texts_one_by_one(texts)

    def _embed_texts_one_by_one(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_model.get_text_embedding(text) for text in texts]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))
