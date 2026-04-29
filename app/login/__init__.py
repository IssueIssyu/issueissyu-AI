"""
JWT 인증(검증) 유틸. `CurrentUserDep` 등 `Depends` 타입은 `app.core.deps`에서 import 하세요
(이 패키지 `__init__`에서 deps를 re-export 하면 `deps`↔`login` 순환 import 가 납니다).
"""
from app.login.http_auth import (
    ACCESS_TOKEN_COOKIE,
    JwtDep,
    get_access_token_raw,
    get_current_user_id,
    get_optional_user_id,
    http_bearer_optional,
    resolve_bearer_or_cookie_token,
)
from app.login.jwt_token_provider import JwtTokenProvider, get_jwt_token_provider

__all__ = [
    "ACCESS_TOKEN_COOKIE",
    "JwtDep",
    "JwtTokenProvider",
    "get_access_token_raw",
    "get_current_user_id",
    "get_jwt_token_provider",
    "get_optional_user_id",
    "http_bearer_optional",
    "resolve_bearer_or_cookie_token",
]
