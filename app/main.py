from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from starlette.responses import JSONResponse

from app import models  # noqa: F401
from app.core.codes import SuccessCode
from app.core.database import AsyncSessionLocal, Base, async_engine
from app.core.handlers import register_exception_handlers
from app.core.responses import success_response
from app.core.config import settings
from app.routes import enabled_routers
from app.services.VectorStoreService import VectorStoreService
from app.services.vector_domains import DomainVectorConfig, VectorDomain
from app.utils.RedisUtil import get_redis_client
from app.utils.S3Util import S3Util
from app.utils.vector import ensure_pgvector_extension

logger = logging.getLogger(__name__)

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
                database_url=settings.sync_database_url,
                async_database_url=settings.async_database_url,
                api_key=gemini_api_key_secret.get_secret_value(),
                table_name=settings.vector_table_name,
                default_embedding_model=settings.gemini_embedding_model,
                default_embed_dim=settings.vector_embed_dim,
                domain_configs=domain_configs,
                hybrid_search=settings.vector_hybrid_search,
                text_search_config=settings.vector_text_search_config,
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

    try:
        yield
    finally:
        async_redis_client = getattr(app.state, "async_redis_client", None)
        if async_redis_client is not None:
            await async_redis_client.aclose()


app = FastAPI(lifespan=lifespan)

register_exception_handlers(app)
for router in enabled_routers:
    app.include_router(router)


@app.get("/health")
def health() -> JSONResponse:
    return success_response(result={"status": "ok"}, success_code=SuccessCode.OK)
