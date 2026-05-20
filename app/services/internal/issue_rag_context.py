from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services.internal.ai.IssueRagPlannerService import IssueRagPlannerService
from app.services.prompts.issue_pin import format_retrieved_docs_for_pin
from app.services.VectorStoreService import VectorStoreService
from app.services.vector_domains import VectorDomain

logger = logging.getLogger(__name__)

RELIABILITY_RAG_TOP_K = 5


def _ctx_suffix(log_context: str | None) -> str:
    return f" [{log_context}]" if log_context else ""


async def build_rag_context_block_for_reliability(
    *,
    vector_store_service: VectorStoreService | None,
    issue_rag_planner_service: IssueRagPlannerService | None,
    title: str,
    content: str,
    user_coordinates: str,
    top_k: int = RELIABILITY_RAG_TOP_K,
    log_context: str | None = None,
) -> str:
    ctx = _ctx_suffix(log_context)
    if vector_store_service is None or issue_rag_planner_service is None:
        logger.warning("Reliability RAG skipped%s: vector_store or planner not configured", ctx)
        return "(검색 결과 없음)"

    fallback_query = f"title:{title}\ncontent:{content}"
    selected = fallback_query

    if settings.issue_pin_reliability_skip_rag_planner:
        logger.info(
            "Reliability RAG planner skipped%s: using direct query (skip_rag_planner=true)",
            ctx,
        )
    else:
        logger.info("Reliability RAG planner start%s", ctx)
        try:
            rewritten = await issue_rag_planner_service.rewrite_queries(
                title=title,
                content=content,
                user_location=user_coordinates,
            )
            primary = rewritten.get("primary_query")
            keyword = rewritten.get("keyword_query")
            selected = (
                primary.strip()
                if isinstance(primary, str) and primary.strip()
                else (
                    keyword.strip()
                    if isinstance(keyword, str) and keyword.strip()
                    else fallback_query
                )
            )
            logger.info(
                "Reliability RAG planner success%s: selected_query=%r",
                ctx,
                selected[:120],
            )
        except Exception:
            logger.warning(
                "Reliability RAG planner failed%s: fallback to title/content query",
                ctx,
                exc_info=True,
            )
            selected = fallback_query

    try:
        logger.info(
            "Reliability RAG retrieve start%s: query=%r top_k=%d",
            ctx,
            selected[:120],
            top_k,
        )
        hits = await vector_store_service.aretrieve(
            query=selected,
            domain=VectorDomain.COMPLAINT,
            similarity_top_k=top_k,
            filters=None,
        )
        if len(hits) > top_k:
            logger.info(
                "Reliability RAG capped hits%s: raw=%d capped=%d",
                ctx,
                len(hits),
                top_k,
            )
            hits = hits[:top_k]
        rows: list[dict[str, Any]] = []
        for hit in hits:
            node = hit.node
            meta = node.metadata if node.metadata is not None else {}
            rows.append(
                {
                    "text": node.get_content(),
                    "score": hit.score,
                    "metadata": dict(meta) if hasattr(meta, "items") else {},
                },
            )
        logger.info("Reliability RAG retrieve done%s: hits=%d", ctx, len(rows))
        return format_retrieved_docs_for_pin(
            rows,
            rag_queries=[selected],
            rag_filters_applied=False,
        )
    except Exception:
        logger.exception("Reliability RAG vector retrieve failed%s", ctx)
        return "(검색 결과 없음)"
