from __future__ import annotations

from app.core.config import settings
from app.services.ComplaintEmailService import ComplaintEmailService
from app.services.RagRetrievalService import RagRetrievalService
from app.services.VectorStoreService import VectorStoreService
from app.services.internal.ai.gemini_factory import (
    build_complaint_email_llm_service,
    build_complaint_email_vlm_service,
    build_rag_rerank_service,
    build_vlm_service,
)


def build_complaint_email_service(
    *,
    api_key: str,
    vector_store_service: VectorStoreService,
) -> ComplaintEmailService:
    complaint_vlm_service = build_complaint_email_vlm_service(api_key=api_key)
    validation_vlm_service = build_vlm_service(api_key=api_key)
    complaint_llm_service = build_complaint_email_llm_service(api_key=api_key)
    rag_rerank_service = build_rag_rerank_service(api_key=api_key)
    rag_retrieval_service = RagRetrievalService(
        vector_store_service=vector_store_service,
        rerank_service=rag_rerank_service,
        retrieve_top_k=settings.rag_retrieve_top_k,
        rerank_top_k=settings.rag_rerank_top_k,
        enable_rerank=settings.rag_enable_rerank,
        vector_query_mode=settings.rag_vector_query_mode,
    )
    return ComplaintEmailService(
        complaint_vlm_service=complaint_vlm_service,
        pin_validation_vlm_service=validation_vlm_service,
        complaint_llm_service=complaint_llm_service,
        rag_retrieval_service=rag_retrieval_service,
    )
