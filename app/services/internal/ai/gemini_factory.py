from __future__ import annotations

from app.core.codes import ErrorCode
from app.core.config import settings
from app.core.exceptions import raise_business_exception
from app.services.ComplaintEmailVlmService import ComplaintEmailVlmService
from app.services.RagRerankService import RagRerankService
from app.services.internal.ai.ComplaintEmailLLMService import ComplaintEmailLLMService
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.IssueRagPlannerService import IssueRagPlannerService
from app.services.internal.ai.VLMService import VLMService
from app.services.internal.ai.gemini_retry import parse_gemini_model_list


def _gemini_api_key_or_none() -> str | None:
    secret = settings.gemini_api_key
    if secret is None:
        return None
    return secret.get_secret_value()


def require_gemini_api_key() -> str:
    api_key = _gemini_api_key_or_none()
    if api_key is None:
        raise_business_exception(ErrorCode.VLM_NOT_CONFIGURED)
    return api_key


def build_vlm_service(*, api_key: str | None = None) -> VLMService:
    key = api_key or require_gemini_api_key()
    return VLMService(
        api_key=key,
        model_name=settings.gemini_vlm_model,
        fallback_models=parse_gemini_model_list(settings.gemini_vlm_fallback_models),
    )


def build_issue_pin_llm_service(*, model: str | None = None) -> IssuePinLLMService:
    api_key = _gemini_api_key_or_none()
    if api_key is None:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")
    model_name = (model or settings.gemini_pin_text_model).strip()
    fallbacks = parse_gemini_model_list(settings.gemini_pin_text_fallback_models)
    return IssuePinLLMService(
        api_key=api_key,
        model_name=model_name,
        fallback_models=fallbacks,
    )


def build_issue_rag_planner_service(*, api_key: str | None = None) -> IssueRagPlannerService:
    key = api_key or require_gemini_api_key()
    return IssueRagPlannerService(
        api_key=key,
        model_name=settings.gemini_rag_planner_model,
        fallback_models=parse_gemini_model_list(settings.gemini_rag_planner_fallback_models),
    )


def build_complaint_email_vlm_service(*, api_key: str | None = None) -> ComplaintEmailVlmService:
    key = api_key or require_gemini_api_key()
    return ComplaintEmailVlmService(
        api_key=key,
        model=settings.gemini_vlm_model,
    )


def build_complaint_email_llm_service(*, api_key: str | None = None) -> ComplaintEmailLLMService:
    key = api_key or require_gemini_api_key()
    return ComplaintEmailLLMService(
        api_key=key,
        model_name=settings.gemini_pin_text_model,
    )


def build_rag_rerank_service(*, api_key: str | None = None) -> RagRerankService:
    key = api_key or require_gemini_api_key()
    return RagRerankService(
        api_key=key,
        embedding_model=settings.gemini_embedding_model,
        embed_dim=settings.vector_embed_dim,
        embedding_batch_size=settings.gemini_embedding_batch_size,
    )
