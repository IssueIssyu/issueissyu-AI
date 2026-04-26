from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.login.jwt_token_provider import JwtTokenProvider, get_jwt_token_provider

logger = logging.getLogger(__name__)

ACCESS_TOKEN_COOKIE = "accessToken"

# auto_error=False: 쿠키 전용·토큰 없이 호출해도 403 안 남. OpenAPI에 `HTTPBearer` 스키마 등록(Authorize).
http_bearer_optional = HTTPBearer(
    auto_error=False,
    description="액세스 토큰. /docs 의 Authorize · Try it out 에서 Bearer 로 넣을 값.",
)

JwtDep = Annotated[JwtTokenProvider, Depends(get_jwt_token_provider)]


def get_access_token_raw(
    request: Request,
    bearer: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(http_bearer_optional),
    ],
) -> str | None:
    """Bearer 우선(스웨거와 동일), 없으면 `accessToken` 쿠키. 이 `Depends`가 OpenAPI security를 붙임."""
    if bearer is not None:
        return bearer.credentials.strip()
    if request.cookies:
        token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if token and token.strip():
            return token.strip()
    return None


def resolve_bearer_or_cookie_token(request: Request) -> str | None:
    """`HTTPBearer` 없이 요청만 읽을 때(테스트·수동). 동작은 `get_access_token_raw`와 같음."""
    header = request.headers.get("Authorization")
    if header and header.startswith("Bearer "):
        return header[7:].strip()
    if request.cookies:
        token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if token and token.strip():
            return token.strip()
    return None


def get_optional_user_id(
    token: Annotated[str | None, Depends(get_access_token_raw)],
    jwt_provider: JwtDep,
) -> UUID | None:
    """
    토큰 없음·검증 실패·REFRESH 토큰인 경우 `None` (uid 없이 요청만 계속).
    """
    if not token:
        return None
    if not jwt_provider.validate_token(token):
        return None
    if jwt_provider.TOKEN_TYPE_ACCESS != jwt_provider.parse_token_type(token):
        return None
    try:
        uid_str = jwt_provider.parse_uid(token)
        return UUID(uid_str)
    except (ValueError, jwt.PyJWTError) as e:
        logger.debug("optional JWT: %s", e)
        return None


def get_current_user_id(
    token: Annotated[str | None, Depends(get_access_token_raw)],
    jwt_provider: JwtDep,
) -> UUID:
    """ACCESS 토큰으로 uid 추출. 실패 시 401. (인증만)"""
    try:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        if not jwt_provider.validate_token(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        if jwt_provider.TOKEN_TYPE_ACCESS != jwt_provider.parse_token_type(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token required",
            )
        uid_str = jwt_provider.parse_uid(token)
        return UUID(uid_str)
    except HTTPException:
        raise
    except (ValueError, jwt.PyJWTError) as e:
        logger.debug("JWT filter error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from e
