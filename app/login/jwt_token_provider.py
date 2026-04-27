from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import jwt

from app.core.config import settings


class JwtTokenProvider:
    """ACCESS 토큰 **검증**만(서명·만료). 토큰 발급은 하지 않음."""

    CLAIM_TOKEN_TYPE = "typ"
    TOKEN_TYPE_ACCESS = "ACCESS"

    def __init__(self) -> None:
        self._secret = settings.jwt_secret.get_secret_value()
        self._algorithm = settings.jwt_algorithm
        self._timezone = ZoneInfo(settings.jwt_timezone)

    def validate_token(self, token: str) -> bool:
        try:
            self.parse_claims(token)
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            return False
        return True

    def _validate_exp_claim(self, claims: dict[str, Any]) -> None:
        exp = claims.get("exp")
        if exp is None:
            return

        if isinstance(exp, datetime):
            exp_dt = exp if exp.tzinfo is not None else exp.replace(tzinfo=self._timezone)
            exp_ts = exp_dt.timestamp()
        elif isinstance(exp, (int, float)):
            exp_ts = float(exp)
            if exp_ts > 1_000_000_000_000:
                exp_ts /= 1000.0
        else:
            msg = "JWT exp claim has invalid type"
            raise jwt.InvalidTokenError(msg)

        if datetime.now(self._timezone).timestamp() >= exp_ts:
            raise jwt.ExpiredSignatureError("Token has expired")

    def parse_claims(self, token: str) -> dict[str, Any]:
        claims = jwt.decode(
            token,
            self._secret,
            algorithms=[self._algorithm],
            options={"verify_exp": False},
        )
        self._validate_exp_claim(claims)
        return claims

    def parse_uid(self, token: str) -> str:
        claims = self.parse_claims(token)
        sub = claims.get("sub")
        if sub is None or not str(sub).strip():
            msg = "JWT subject (uid) is missing"
            raise jwt.InvalidTokenError(msg)
        return str(sub).strip()

    def parse_token_type(self, token: str) -> str | None:
        claims = self.parse_claims(token)
        typ = claims.get(self.CLAIM_TOKEN_TYPE)
        return str(typ) if typ is not None else None


@lru_cache
def get_jwt_token_provider() -> JwtTokenProvider:
    return JwtTokenProvider()
