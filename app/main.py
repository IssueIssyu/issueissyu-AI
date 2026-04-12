from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app import models  # noqa: F401
from app.core.codes import SuccessCode
from app.core.database import AsyncSessionLocal, Base, async_engine
from app.core.handlers import register_exception_handlers
from app.core.responses import success_response
from app.routes import user_router
from app.utils.vector import ensure_pgvector_extension

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
    yield


app = FastAPI(lifespan=lifespan)

register_exception_handlers(app)
app.include_router(user_router)


@app.get("/health")
def health() -> dict:
    return success_response(result={"status": "ok"}, success_code=SuccessCode.OK)
