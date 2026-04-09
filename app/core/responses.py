from typing import Any, Generic, Optional, TypeVar

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

T = TypeVar("T")


class SuccessEnvelope(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    meta: Optional[dict[str, Any]] = None


def success_response(
    data: Any = None,
    *,
    meta: Optional[dict[str, Any]] = None,
    status_code: int = 200,
    headers: Optional[dict[str, str]] = None,
) -> JSONResponse:
    payload = SuccessEnvelope(success=True, data=data, meta=meta)
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload.model_dump(exclude_none=True)),
        headers=headers,
    )
