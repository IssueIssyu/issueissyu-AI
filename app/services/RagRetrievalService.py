from __future__ import annotations

import logging
from typing import Any

from llama_index.core.vector_stores import MetadataFilters

from app.schemas.ComplaintEmailDTO import ComplaintEmailRagHit
from app.services.RagRerankService import RagRerankCandidate, RagRerankService
from app.services.vector_domains import VectorDomain
from app.services.VectorStoreService import VectorStoreService

logger = logging.getLogger(__name__)


class RagRetrievalService:
    # 벡터 검색(top-k) > rerank > LLM용 문맥

    def __init__(
        self,
        *,
        vector_store_service: VectorStoreService,
        rerank_service: RagRerankService,
        retrieve_top_k: int = 10,
        rerank_top_k: int = 5,
    ) -> None:
        self._vector_store = vector_store_service
        self._rerank_service = rerank_service
        self._retrieve_top_k = max(1, retrieve_top_k)
        self._rerank_top_k = max(1, rerank_top_k)

    async def retrieve_and_rerank(
        self,
        query: str,
        *,
        domain: VectorDomain | str | None = VectorDomain.COMPLAINT,
        filters: MetadataFilters | None = None,
        retrieve_top_k: int | None = None,
        rerank_top_k: int | None = None,
    ) -> list[ComplaintEmailRagHit]:
        fetch_k = retrieve_top_k if retrieve_top_k is not None else self._retrieve_top_k
        keep_k = rerank_top_k if rerank_top_k is not None else self._rerank_top_k
        fetch_k = max(fetch_k, keep_k)

        nodes = await self._vector_store.aretrieve(
            query=query,
            domain=domain,
            similarity_top_k=fetch_k,
            filters=filters,
        )
        candidates = self._candidates_from_nodes(nodes)
        if not candidates:
            return []

        reranked = await self._rerank_service.rerank(
            query,
            candidates,
            top_n=keep_k,
        )
        return self._hits_from_reranked(reranked)

    @staticmethod
    def _candidates_from_nodes(nodes: Any) -> list[RagRerankCandidate]:
        rows: list[RagRerankCandidate] = []
        for hit in nodes:
            node = hit.node
            text = (node.get_content() or "").strip()
            if not text:
                continue
            meta = node.metadata if node.metadata is not None else {}
            rows.append(
                RagRerankCandidate(
                    text=text,
                    payload={
                        "metadata": dict(meta) if hasattr(meta, "items") else {},
                        "retrieval_score": hit.score,
                    },
                    retrieval_score=hit.score,
                ),
            )
        return rows

    @staticmethod
    def _hits_from_reranked(
        reranked: list[tuple[float, RagRerankCandidate]],
    ) -> list[ComplaintEmailRagHit]:
        hits: list[ComplaintEmailRagHit] = []
        for rerank_score, candidate in reranked:
            payload = candidate.payload if isinstance(candidate.payload, dict) else {}
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            retrieval_score = candidate.retrieval_score
            if retrieval_score is None and isinstance(payload.get("retrieval_score"), (int, float)):
                retrieval_score = float(payload["retrieval_score"])
            hits.append(
                ComplaintEmailRagHit(
                    text=candidate.text,
                    retrieval_score=retrieval_score,
                    rerank_score=rerank_score,
                    metadata=metadata,
                ),
            )
        return hits
