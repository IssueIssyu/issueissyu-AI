from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from starlette.responses import JSONResponse

from app import models  # noqa: F401
from app.core.codes import SuccessCode
from app.core.database import AsyncSessionLocal, Base, async_engine
from app.core.handlers import register_exception_handlers
from app.core.responses import success_response
from app.routes import enabled_routers
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
