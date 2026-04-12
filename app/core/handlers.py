import json
import os
from typing import Any, Callable

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.codes import ErrorCode, SuccessCode
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


def _should_wrap_success_envelope() -> bool:
    return os.getenv("WRAP_SUCCESS_RESPONSES", "false").lower() in ("1", "true", "yes")


class SuccessEnvelopeMiddleware(BaseHTTPMiddleware):
    """2xx JSON 응답을 ApiResponse 형태로 감쌉니다. 이미 isSuccess 키가 있으면 그대로 둡니다."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        if not _should_wrap_success_envelope():
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response
        ct = response.headers.get("content-type", "")
        if "application/json" not in ct:
            return response

        body = getattr(response, "body", None)
        if body is None:
            chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            body = b"".join(chunks)
        else:
            body = bytes(body)

        try:
            parsed: Any = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

        if isinstance(parsed, dict) and parsed.get("isSuccess") is True:
            return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

        success_code = SuccessCode.CREATED if response.status_code == status.HTTP_201_CREATED else SuccessCode.OK
        wrapped = {
            "isSuccess": True,
            "code": success_code.code,
            "message": success_code.message,
            "result": parsed,
        }
        return JSONResponse(
            content=wrapped,
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
        )


def register_success_envelope_middleware(app: FastAPI) -> None:
    if _should_wrap_success_envelope():
        app.add_middleware(SuccessEnvelopeMiddleware)
