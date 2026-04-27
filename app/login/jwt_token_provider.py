from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt

from app.core.config import settings


class JwtTokenProvider:
    """ACCESS 토큰 **검증**만(서명·만료). 토큰 발급은 하지 않음."""

    CLAIM_TOKEN_TYPE = "typ"
    TOKEN_TYPE_ACCESS = "ACCESS"

    def __init__(self) -> None:
        self._secret = settings.jwt_secret.get_secret_value()
        self._algorithm = settings.jwt_algorithm

    def validate_token(self, token: str) -> bool:
        try:
            self.parse_claims(token)
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            return False
        return True

    def _validate_exp_claim_format(self, claims: dict[str, Any]) -> None:
        exp = claims.get("exp")
        if exp is None:
            msg = "JWT exp claim is missing"
            raise jwt.InvalidTokenError(msg)

        if isinstance(exp, (int, float)):
            exp_ts = float(exp)
            if exp_ts > 1_000_000_000_000:
                msg = "JWT exp claim must be seconds, not milliseconds"
                raise jwt.InvalidTokenError(msg)
        else:
            msg = "JWT exp claim has invalid type"
            raise jwt.InvalidTokenError(msg)

    def parse_claims(self, token: str) -> dict[str, Any]:
        unverified_claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
            algorithms=[self._algorithm],
        )
        self._validate_exp_claim_format(unverified_claims)

        claims = jwt.decode(
            token,
            self._secret,
            algorithms=[self._algorithm],
            options={"require": ["exp"], "verify_exp": True},
        )
        return claims

    def parse_uid_from_claims(self, claims: dict[str, Any]) -> str:
        sub = claims.get("sub")
        if sub is None or not str(sub).strip():
            msg = "JWT subject (uid) is missing"
            raise jwt.InvalidTokenError(msg)
        return str(sub).strip()

    def parse_uid(self, token: str) -> str:
        claims = self.parse_claims(token)
        return self.parse_uid_from_claims(claims)

    def parse_token_type_from_claims(self, claims: dict[str, Any]) -> str | None:
        typ = claims.get(self.CLAIM_TOKEN_TYPE)
        return str(typ) if typ is not None else None

    def parse_token_type(self, token: str) -> str | None:
        claims = self.parse_claims(token)
        return self.parse_token_type_from_claims(claims)


@lru_cache
def get_jwt_token_provider() -> JwtTokenProvider:
    return JwtTokenProvider()
