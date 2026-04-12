from typing import Any, Generic, Optional, TypeVar

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.codes import ErrorCode, SuccessCode

T = TypeVar("T")


class SuccessEnvelope(BaseModel, Generic[T]):
    isSuccess: bool = True
    code: str
    message: str
    result: Optional[T] = None


class ErrorEnvelope(BaseModel, Generic[T]):
    isSuccess: bool = False
    code: str
    message: str
    result: Optional[T] = None


def success_response(
    result: Any = None,
    *,
    success_code: SuccessCode = SuccessCode.OK,
    status_code: Optional[int] = None,
    headers: Optional[dict[str, str]] = None,
) -> JSONResponse:
    resolved_status_code = status_code or success_code.http_status
    payload = SuccessEnvelope(
        isSuccess=True,
        code=success_code.code,
        message=success_code.message,
        result=result,
    )
    return JSONResponse(
        status_code=resolved_status_code,
        content=jsonable_encoder(payload.model_dump(exclude_none=True)),
        headers=headers,
    )


def failure_response(
    *,
    error_code: ErrorCode,
    result: Any = None,
    status_code: Optional[int] = None,
    headers: Optional[dict[str, str]] = None,
) -> JSONResponse:
    resolved_status_code = status_code or error_code.http_status
    payload = ErrorEnvelope(
        isSuccess=False,
        code=error_code.code,
        message=error_code.message,
        result=result,
    )
    return JSONResponse(
        status_code=resolved_status_code,
        content=jsonable_encoder(payload.model_dump()),
        headers=headers,
    )
