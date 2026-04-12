from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import AsyncSessionLocal
from app.core.handlers import register_exception_handlers, register_success_envelope_middleware
from app.utils.vector import ensure_pgvector_extension


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with AsyncSessionLocal() as session:
        await ensure_pgvector_extension(session)
        await session.commit()
    yield


app = FastAPI(lifespan=lifespan)

register_exception_handlers(app)
register_success_envelope_middleware(app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
