from contextlib import asynccontextmanager
import logging
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app import models  # noqa: F401
from app.core.codes import SuccessCode
from app.core.database import AsyncSessionLocal
from app.core.handlers import register_exception_handlers
from app.core.responses import success_response
from app.core.config import settings
from app.routes import enabled_routers
from app.services.internal.ComplaintEmailPdfService import ComplaintEmailPdfService
from app.services.ComplaintEmailService import ComplaintEmailService
from app.services.ComplaintEmailVlmService import ComplaintEmailVlmService
from app.services.RagRerankService import RagRerankService
from app.services.RagRetrievalService import RagRetrievalService
from app.services.VectorStoreService import VectorStoreService
from app.services.internal.ComplaintPetitionSchedulerService import ComplaintPetitionSchedulerService
from app.services.internal.ai.ComplaintEmailLLMService import ComplaintEmailLLMService
from app.services.internal.ai.VLMService import VLMService
from app.services.internal.ai.gemini_retry import parse_gemini_model_list
from app.services.vector_domains import DomainVectorConfig, VectorDomain
from app.utils.RedisUtil import get_redis_client
from app.utils.S3Util import S3Util
from app.utils.vector import ensure_pgvector_extension

logger = logging.getLogger(__name__)


def _configure_local_logging() -> None:
    if settings.env != "local":
        return
    root_logger = logging.getLogger()
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)
    logging.getLogger("app").setLevel(logging.INFO)
    logger.info("Local logging level configured to INFO")


_configure_local_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):

    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    """

    async with AsyncSessionLocal() as session:
        try:
            await ensure_pgvector_extension(session)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "pgvector extension setup skipped; continuing without vector extension: %s",
                exc,
            )

    gemini_api_key_secret = settings.gemini_api_key
    if gemini_api_key_secret is None:
        logger.warning("GEMINI_API_KEY is not configured. VectorStoreService initialization skipped.")
    else:
        try:
            # 도메인별 임베딩 모델/차원 라우팅 (필요 시 여기 확장)
            domain_configs = {
                VectorDomain.COMPLAINT: DomainVectorConfig(
                    table_name="complaint",
                    embedding_model=settings.gemini_embedding_model,
                    embed_dim=settings.vector_embed_dim,
                ),
                VectorDomain.FESTIVAL: DomainVectorConfig(
                    table_name="festival",
                    embedding_model=settings.gemini_embedding_model,
                    embed_dim=settings.vector_embed_dim,
                ),
                VectorDomain.POLICY: DomainVectorConfig(
                    table_name="policy",
                    embedding_model=settings.gemini_embedding_model,
                    embed_dim=settings.vector_embed_dim,
                ),
                VectorDomain.CONTEST: DomainVectorConfig(
                    table_name="contest",
                    embedding_model=settings.gemini_embedding_model,
                    embed_dim=settings.vector_embed_dim,
                ),
            }
            app.state.vector_store_service = VectorStoreService(
                api_key=gemini_api_key_secret.get_secret_value(),
                table_name=settings.vector_table_name,
                default_embedding_model=settings.gemini_embedding_model,
                default_embed_dim=settings.vector_embed_dim,
                domain_configs=domain_configs,
                hybrid_search=settings.vector_hybrid_search,
                text_search_config=settings.vector_text_search_config,
                embedding_batch_size_override=settings.gemini_embedding_batch_size,
            )
            if settings.vector_dim_check:
                dimension_checks = (
                    await app.state.vector_store_service.avalidate_embedding_dimensions()
                )
                for check in dimension_checks:
                    if check["matched"]:
                        logger.info(
                            "Vector embedding dimension OK: model=%s expected=%s actual=%s",
                            check["model_name"],
                            check["expected_dim"],
                            check["actual_dim"],
                        )
                    else:
                        logger.error(
                            "Vector embedding dimension mismatch: model=%s expected=%s actual=%s",
                            check["model_name"],
                            check["expected_dim"],
                            check["actual_dim"],
                        )
            else:
                logger.debug(
                    "Skipping vector embedding dimension probe at startup "
                    "(set VECTOR_DIM_CHECK=true to enable).",
                )
        except Exception as exc:
            logger.warning("VectorStoreService initialization failed: %s", exc)

    app.state.s3_util = S3Util()
    app.state.async_redis_client = get_redis_client(async_mode=True)
    app.state.shared_httpx_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.location_resolve_timeout_seconds),
    )

    try:
        await run_in_threadpool(ComplaintEmailPdfService.start_playwright_browser)
    except Exception as exc:
        logger.warning(
            "Playwright PDF browser startup skipped; PDF fallback may lazy-start: %s",
            exc,
        )

    scheduler = None
    if (
        gemini_api_key_secret is not None
        and getattr(app.state, "vector_store_service", None) is not None
    ):
        try:
            complaint_vlm_service = ComplaintEmailVlmService(
                api_key=gemini_api_key_secret.get_secret_value(),
                model=settings.gemini_vlm_model,
            )
            validation_vlm_service = VLMService(
                api_key=gemini_api_key_secret.get_secret_value(),
                model_name=settings.gemini_vlm_model,
                fallback_models=parse_gemini_model_list(settings.gemini_vlm_fallback_models),
            )
            complaint_llm_service = ComplaintEmailLLMService(
                api_key=gemini_api_key_secret.get_secret_value(),
                model_name=settings.gemini_pin_text_model,
            )
            rag_rerank_service = RagRerankService(
                api_key=gemini_api_key_secret.get_secret_value(),
                embedding_model=settings.gemini_embedding_model,
                embed_dim=settings.vector_embed_dim,
                embedding_batch_size=settings.gemini_embedding_batch_size,
            )
            rag_retrieval_service = RagRetrievalService(
                vector_store_service=app.state.vector_store_service,
                rerank_service=rag_rerank_service,
                retrieve_top_k=settings.rag_retrieve_top_k,
                rerank_top_k=settings.rag_rerank_top_k,
                enable_rerank=settings.rag_enable_rerank,
                vector_query_mode=settings.rag_vector_query_mode,
            )
            complaint_email_service = ComplaintEmailService(
                complaint_vlm_service=complaint_vlm_service,
                pin_validation_vlm_service=validation_vlm_service,
                complaint_llm_service=complaint_llm_service,
                rag_retrieval_service=rag_retrieval_service,
            )
            scheduler = ComplaintPetitionSchedulerService(
                complaint_email_service=complaint_email_service,
                s3_util=app.state.s3_util,
            )
            scheduler.start()
            app.state.complaint_scheduler = scheduler
        except Exception as exc:
            logger.warning("Complaint scheduler initialization failed: %s", exc)

    try:
        yield
    finally:
        scheduler = getattr(app.state, "complaint_scheduler", None)
        if scheduler is not None:
            await scheduler.stop()
        try:
            await run_in_threadpool(ComplaintEmailPdfService.stop_playwright_browser)
        except Exception as exc:
            logger.warning("Playwright PDF browser shutdown failed: %s", exc)

        hx = getattr(app.state, "shared_httpx_client", None)
        if hx is not None:
            await hx.aclose()
        async_redis_client = getattr(app.state, "async_redis_client", None)
        if async_redis_client is not None:
            await async_redis_client.aclose()


app = FastAPI(lifespan=lifespan)


def _patch_binary_media_schema(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "string" and node.get("contentMediaType") == "application/octet-stream":
            node.pop("contentMediaType", None)
            node["format"] = "binary"
        for value in node.values():
            _patch_binary_media_schema(value)
        return
    if isinstance(node, list):
        for item in node:
            _patch_binary_media_schema(item)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    _patch_binary_media_schema(openapi_schema)
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

register_exception_handlers(app)
for router in enabled_routers:
    app.include_router(router)


@app.get("/health")
def health() -> JSONResponse:
    return success_response(result={"status": "ok"}, success_code=SuccessCode.OK)
