from fastapi import FastAPI

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException
from app.core.handlers import register_exception_handlers, register_success_envelope_middleware

app = FastAPI()

register_exception_handlers(app)
register_success_envelope_middleware(app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

