from contextlib import asynccontextmanager
import asyncio
import logging
import sys
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from starlette.responses import JSONResponse

from app import models  # noqa: F401
from app.core.codes import SuccessCode
from app.core.database import AsyncSessionLocal
from app.core.handlers import register_exception_handlers
from app.core.responses import success_response
from app.core.config import settings
from app.routes import enabled_routers
from app.services.internal.ComplaintEmailPdfService import ComplaintEmailPdfService
from app.services.internal.ComplaintPetitionSchedulerService import ComplaintPetitionSchedulerService
from app.services.internal.ContestPinSchedulerService import ContestPinSchedulerService
from app.services.internal.PolicyPinSchedulerService import PolicyPinSchedulerService
from app.services.internal.complaint_wiring import build_complaint_email_service
from app.services.internal.ai.gemini_key_pool import init_gemini_key_pool
from app.services.VectorStoreService import VectorStoreService
from app.services.vector_domains import build_hnsw_kwargs, build_vector_domain_configs
from app.schemas.IssueDTO import (
    CreateIssuePinMultipartRequest,
    PinImageIsMainItem,
    UpdateIssuePinImageUrlItem,
    UpdateIssuePinMultipartRequest,
)
from app.utils.openapi_multipart import patch_multipart_json_request_field, register_pydantic_models
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


def _configure_windows_event_loop_for_subprocess() -> None:
    """
    Windows에서 asyncio subprocess_exec가 NotImplementedError가 나는 경우가 있습니다.
    Playwright(Chromium) 같은 컴포넌트가 subprocess를 띄우기 때문에
    이벤트 루프 정책을 Proactor로 맞춰줍니다.
    """
    if sys.platform != "win32":
        return

    try:
        policy = asyncio.get_event_loop_policy()
        if policy.__class__.__name__ == "WindowsSelectorEventLoopPolicy":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            logger.info("Windows event loop policy switched to Proactor for subprocess support.")
    except Exception:
        # 정책 변경 실패해도 서버 자체는 계속 동작해야 합니다.
        logger.debug("Windows event loop policy switch failed", exc_info=True)


_configure_local_logging()
_configure_windows_event_loop_for_subprocess()


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

    gemini_api_keys = settings.resolved_gemini_api_keys()
    gemini_key_pool = init_gemini_key_pool()
    if gemini_key_pool is not None:
        app.state.gemini_key_pool = gemini_key_pool
        logger.info(
            "Gemini key pool initialized: %d key(s), rotation=%s",
            gemini_key_pool.size,
            "on" if gemini_key_pool.enabled else "off",
        )
    else:
        logger.warning("GEMINI_API_KEY is not configured. VectorStoreService initialization skipped.")

    if gemini_api_keys:
        try:
            domain_configs = build_vector_domain_configs(settings)
            app.state.vector_store_service = VectorStoreService(
                api_key=gemini_api_keys[0],
                table_name=settings.vector_table_name,
                default_embedding_model=settings.gemini_embedding_model,
                default_embed_dim=settings.vector_embed_dim,
                domain_configs=domain_configs,
                hybrid_search=settings.vector_hybrid_search,
                text_search_config=settings.vector_text_search_config,
                embedding_batch_size_override=settings.gemini_embedding_batch_size,
                hnsw_kwargs=build_hnsw_kwargs(settings),
                key_pool=gemini_key_pool,
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
        await ComplaintEmailPdfService.start_playwright_browser()
    except Exception as exc:
        logger.warning(
            "Playwright PDF browser startup skipped; PDF fallback may lazy-start: %s",
            exc,
        )

    complaint_scheduler = None
    if (
        gemini_api_keys
        and getattr(app.state, "vector_store_service", None) is not None
    ):
        try:
            complaint_email_service = build_complaint_email_service(
                api_key=gemini_api_keys[0],
                vector_store_service=app.state.vector_store_service,
            )
            complaint_scheduler = ComplaintPetitionSchedulerService(
                complaint_email_service=complaint_email_service,
                s3_util=app.state.s3_util,
            )
            complaint_scheduler.start()
            app.state.complaint_scheduler = complaint_scheduler
        except Exception as exc:
            logger.warning("Complaint scheduler initialization failed: %s", exc)

    policy_pin_scheduler = None
    if settings.policy_news_service_key is not None and gemini_api_keys:
        try:
            policy_pin_scheduler = PolicyPinSchedulerService(s3_util=app.state.s3_util)
            policy_pin_scheduler.start()
            app.state.policy_pin_scheduler = policy_pin_scheduler
        except Exception as exc:
            logger.warning("Policy pin scheduler initialization failed: %s", exc)

    contest_pin_scheduler = None
    if gemini_api_keys:
        try:
            contest_pin_scheduler = ContestPinSchedulerService(s3_util=app.state.s3_util)
            contest_pin_scheduler.start()
            app.state.contest_pin_scheduler = contest_pin_scheduler
        except Exception as exc:
            logger.warning("Contest pin scheduler initialization failed: %s", exc)

    try:
        yield
    finally:
        complaint_scheduler = getattr(app.state, "complaint_scheduler", None)
        if complaint_scheduler is not None:
            try:
                await complaint_scheduler.stop()
            except Exception as exc:
                logger.warning("Complaint scheduler stop failed: %s", exc)
        policy_pin_scheduler = getattr(app.state, "policy_pin_scheduler", None)
        if policy_pin_scheduler is not None:
            try:
                await policy_pin_scheduler.stop()
            except Exception as exc:
                logger.warning("Policy pin scheduler stop failed: %s", exc)
        contest_pin_scheduler = getattr(app.state, "contest_pin_scheduler", None)
        if contest_pin_scheduler is not None:
            try:
                await contest_pin_scheduler.stop()
            except Exception as exc:
                logger.warning("Contest pin scheduler stop failed: %s", exc)
        try:
            await ComplaintEmailPdfService.stop_playwright_browser()
        except Exception as exc:
            logger.warning("Playwright PDF browser shutdown failed: %s", exc)

        hx = getattr(app.state, "shared_httpx_client", None)
        if hx is not None:
            try:
                await hx.aclose()
            except Exception as exc:
                logger.warning("Shared HTTPX client close failed: %s", exc)
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
    register_pydantic_models(
        openapi_schema,
        PinImageIsMainItem,
        UpdateIssuePinImageUrlItem,
        CreateIssuePinMultipartRequest,
        UpdateIssuePinMultipartRequest,
    )
    patch_multipart_json_request_field(
        openapi_schema,
        body_schema_key="Body_create_issue_pin_issues_pin_post",
        request_model=CreateIssuePinMultipartRequest,
        description=(
            "JSON part (Content-Type: application/json). "
            "photos와 pinImages 길이·순서 1:1, 이미지 1장 이상이면 isMain true 정확히 1개."
        ),
        example={
            "lat": 37.566535,
            "lng": 126.977969,
            "pinTitle": "횡단보도 신호등 고장",
            "pinContent": "신호등이 3일째 작동하지 않습니다.",
            "pinImages": [{"isMain": True}],
        },
    )
    patch_multipart_json_request_field(
        openapi_schema,
        body_schema_key="Body_update_issue_pin_issues_pin__pin_id__patch",
        request_model=UpdateIssuePinMultipartRequest,
        description=(
            "JSON part (Content-Type: application/json). "
            "pinImageUrls 생략+photos 없음=기존 이미지 유지, photos 있을 때 pinImages 필수."
        ),
        example={
            "pinTitle": "수정된 제목",
            "pinContent": "수정된 본문",
            "pinImageUrls": [{"pinImageUrl": "https://example.com/a.jpg", "isMain": True}],
        },
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

register_exception_handlers(app)
for router in enabled_routers:
    app.include_router(router)


@app.get("/health")
def health() -> JSONResponse:
    return success_response(result={"status": "ok"}, success_code=SuccessCode.OK)

@app.get("/")
def default_route() -> JSONResponse:
    return success_response(result={"status": "issueissyu서비스의 AI 서버입니다."}, success_code=SuccessCode.OK)