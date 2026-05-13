import json
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.codes import ErrorCode
from app.core.exceptions import CustomException, create_http_exception
from app.core.responses import failure_response


def _error_response(http_status: int, code: ErrorCode, result: Any = None, message: str | None = None) -> JSONResponse:
    response = failure_response(error_code=code, result=result, status_code=http_status)
    if message is None or message == code.message:
        return response
    payload = json.loads(response.body.decode("utf-8"))
    payload["message"] = message
    return JSONResponse(status_code=http_status, content=payload)


async def custom_exception_handler(request: Request, exc: CustomException) -> JSONResponse:
    http_exc = create_http_exception(exc)
    return _error_response(
        http_status=http_exc.status_code,
        code=exc.error_code,
        message=exc.detail,
        result=exc.extra if exc.extra else None,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        raw_code = detail.get("code")
        matched = next((ec for ec in ErrorCode if ec.code == raw_code), ErrorCode.INTERNAL_SERVER_ERROR)
        return _error_response(
            http_status=exc.status_code,
            code=matched,
            message=str(detail.get("message", "")),
            result=detail.get("result"),
        )
    message = detail if isinstance(detail, str) else str(detail)
    ec = ErrorCode.INTERNAL_SERVER_ERROR
    return _error_response(http_status=exc.status_code, code=ec, message=message)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    ec = ErrorCode.VALIDATION_ERROR
    return _error_response(
        http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code=ec,
        result={"errors": exc.errors()},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    ec = ErrorCode.INTERNAL_SERVER_ERROR
    return _error_response(http_status=status.HTTP_500_INTERNAL_SERVER_ERROR, code=ec)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CustomException, custom_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
