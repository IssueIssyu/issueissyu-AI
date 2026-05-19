from __future__ import annotations

import logging
from typing import Any

from llama_index.core.vector_stores.types import MetadataFilters

from app.schemas.ComplaintEmailDTO import ComplaintEmailRagHit, ComplaintEmailRagPipelineResult
from app.services.RagRerankService import RagRerankCandidate, RagRerankService
from app.services.vector_domains import VectorDomain
from app.services.VectorStoreService import VectorStoreService

logger = logging.getLogger(__name__)


class RagRetrievalService:
    # 벡터 검색(top-k) > (선택) rerank > LLM용 문맥

    def __init__(
        self,
        *,
        vector_store_service: VectorStoreService,
        rerank_service: RagRerankService,
        retrieve_top_k: int = 10,
        rerank_top_k: int = 5,
        enable_rerank: bool = False,
        vector_query_mode: str = "default",
    ) -> None:
        self._vector_store = vector_store_service
        self._rerank_service = rerank_service
        self._retrieve_top_k = max(1, retrieve_top_k)
        self._rerank_top_k = max(1, rerank_top_k)
        self._enable_rerank = enable_rerank
        self._vector_query_mode = (vector_query_mode or "default").strip() or "default"

    async def retrieve_and_rerank(
        self,
        query: str,
        *,
        domain: VectorDomain | str | None = VectorDomain.COMPLAINT,
        filters: MetadataFilters | None = None,
        retrieve_top_k: int | None = None,
        rerank_top_k: int | None = None,
    ) -> list[ComplaintEmailRagHit]:
        pipeline = await self.retrieve_and_rerank_pipeline(
            query,
            domain=domain,
            filters=filters,
            retrieve_top_k=retrieve_top_k,
            rerank_top_k=rerank_top_k,
        )
        return pipeline.reranked_hits

    async def retrieve_and_rerank_pipeline(
        self,
        query: str,
        *,
        domain: VectorDomain | str | None = VectorDomain.COMPLAINT,
        filters: MetadataFilters | None = None,
        retrieve_top_k: int | None = None,
        rerank_top_k: int | None = None,
    ) -> ComplaintEmailRagPipelineResult:
        rag_query = (query or "").strip()
        fetch_k = retrieve_top_k if retrieve_top_k is not None else self._retrieve_top_k
        keep_k = rerank_top_k if rerank_top_k is not None else self._rerank_top_k
        if self._enable_rerank:
            fetch_k = max(fetch_k, keep_k)
        else:
            keep_k = min(keep_k, fetch_k)

        try:
            nodes = await self._vector_store.aretrieve(
                query=rag_query,
                domain=domain,
                similarity_top_k=fetch_k,
                filters=filters,
                vector_store_query_mode=self._vector_query_mode,
            )
        except Exception:
            logger.exception("RAG retrieve failed — query=%r", rag_query)
            return ComplaintEmailRagPipelineResult(rag_query=rag_query)

        candidates = self._candidates_from_nodes(nodes)
        candidates = self._top_candidates_by_retrieval(candidates, fetch_k)
        if not candidates:
            return ComplaintEmailRagPipelineResult(rag_query=rag_query)

        retrieval_hits = self._hits_from_candidates(candidates)
        if self._enable_rerank:
            try:
                reranked = await self._rerank_service.rerank(
                    rag_query,
                    candidates,
                    top_n=keep_k,
                )
                reranked_hits = self._hits_from_reranked(reranked)
            except Exception:
                logger.exception("RAG rerank failed — falling back to retrieval scores")
                reranked_hits = self._hits_from_candidates(
                    self._top_candidates_by_retrieval(candidates, keep_k),
                )
        else:
            reranked_hits = self._hits_from_candidates(
                self._top_candidates_by_retrieval(candidates, keep_k),
            )

        return ComplaintEmailRagPipelineResult(
            rag_query=rag_query,
            retrieval_hits=retrieval_hits,
            reranked_hits=reranked_hits,
        )

    @staticmethod
    def _json_safe_metadata(meta: Any) -> dict[str, str | int | float | bool | None]:
        if not hasattr(meta, "items"):
            return {}
        safe: dict[str, str | int | float | bool | None] = {}
        for key, value in meta.items():
            name = str(key)
            if value is None or isinstance(value, (str, int, float, bool)):
                safe[name] = value
            else:
                safe[name] = str(value)
        return safe

    @staticmethod
    def _top_candidates_by_retrieval(
        candidates: list[RagRerankCandidate],
        limit: int,
    ) -> list[RagRerankCandidate]:
        if limit < 1 or not candidates:
            return []
        ranked = sorted(
            candidates,
            key=lambda row: row.retrieval_score if row.retrieval_score is not None else float("-inf"),
            reverse=True,
        )
        return ranked[:limit]

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
                        "metadata": RagRetrievalService._json_safe_metadata(meta),
                        "retrieval_score": hit.score,
                    },
                    retrieval_score=hit.score,
                ),
            )
        return rows

    @staticmethod
    def _hits_from_candidates(candidates: list[RagRerankCandidate]) -> list[ComplaintEmailRagHit]:
        hits: list[ComplaintEmailRagHit] = []
        for candidate in candidates:
            payload = candidate.payload if isinstance(candidate.payload, dict) else {}
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            retrieval_score = candidate.retrieval_score
            if retrieval_score is None and isinstance(payload.get("retrieval_score"), (int, float)):
                retrieval_score = float(payload["retrieval_score"])
            hits.append(
                ComplaintEmailRagHit(
                    text=candidate.text,
                    retrieval_score=retrieval_score,
                    rerank_score=None,
                    metadata=metadata,
                ),
            )
        return hits

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
