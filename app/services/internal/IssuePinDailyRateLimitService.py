from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from redis.asyncio import Redis as AsyncRedis

from app.core.codes import ErrorCode
from app.core.config import settings
from app.core.exceptions import raise_business_exception

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_EXPIRE_BUFFER_SECONDS = 60 * 60

_RECORD_DAILY_SUCCESS_LUA = """
local n = tonumber(redis.call('GET', KEYS[1]) or '0')
if n >= tonumber(ARGV[2]) then
  return {0, n}
end
n = redis.call('INCR', KEYS[1])
if n == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {1, n}
"""


class RateLimitKind(StrEnum):
    AI = "ai"
    CREATE = "create"
    EDIT = "edit"


_KEY_PREFIX_BY_KIND: dict[RateLimitKind, str] = {
    RateLimitKind.AI: "issue_pin:ai:daily",
    RateLimitKind.CREATE: "issue_pin:create:daily",
    RateLimitKind.EDIT: "issue_pin:edit:daily",
}

_ERROR_CODE_BY_KIND: dict[RateLimitKind, ErrorCode] = {
    RateLimitKind.AI: ErrorCode.AI_PIN_GENERATION_RATE_LIMIT_EXCEEDED,
    RateLimitKind.CREATE: ErrorCode.ISSUE_PIN_CREATE_RATE_LIMIT_EXCEEDED,
    RateLimitKind.EDIT: ErrorCode.ISSUE_PIN_EDIT_RATE_LIMIT_EXCEEDED,
}


@dataclass(frozen=True, slots=True)
class RateLimitSnapshot:
    daily_limit: int
    used_count: int
    reset_at: datetime

    @property
    def remaining_count(self) -> int:
        return max(0, self.daily_limit - self.used_count)

    def to_result_dict(self) -> dict[str, int | str]:
        return {
            "dailyLimit": self.daily_limit,
            "usedCount": self.used_count,
            "resetAt": self.reset_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class IssuePinQuotaStatus:
    enabled: bool
    daily_limit: int
    used_count: int
    reset_at: datetime

    @property
    def remaining_count(self) -> int:
        if not self.enabled:
            return self.daily_limit
        return max(0, self.daily_limit - self.used_count)

    def to_result_dict(self) -> dict[str, bool | int | str]:
        return {
            "enabled": self.enabled,
            "dailyLimit": self.daily_limit,
            "usedCount": self.used_count,
            "remainingCount": self.remaining_count,
            "resetAt": self.reset_at.isoformat(),
        }


class IssuePinDailyRateLimitService:
    def __init__(self, *, redis_client: AsyncRedis | None = None) -> None:
        self._redis_client = redis_client
        self._record_success_script = (
            redis_client.register_script(_RECORD_DAILY_SUCCESS_LUA)
            if redis_client is not None
            else None
        )

    @staticmethod
    def daily_key(
        *,
        kind: RateLimitKind,
        subject_id: str,
        kst_date: datetime,
    ) -> str:
        prefix = _KEY_PREFIX_BY_KIND[kind]
        return f"{prefix}:{subject_id}:{kst_date.strftime('%Y%m%d')}"

    @staticmethod
    def seconds_until_kst_midnight(*, now: datetime | None = None) -> int:
        current = now or datetime.now(_KST)
        if current.tzinfo is None:
            current = current.replace(tzinfo=_KST)
        else:
            current = current.astimezone(_KST)
        next_midnight = (current + timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return int((next_midnight - current).total_seconds()) + _EXPIRE_BUFFER_SECONDS

    @staticmethod
    def next_kst_midnight(*, now: datetime | None = None) -> datetime:
        current = now or datetime.now(_KST)
        if current.tzinfo is None:
            current = current.replace(tzinfo=_KST)
        else:
            current = current.astimezone(_KST)
        return (current + timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _resolve_subject_id(
        *,
        kind: RateLimitKind,
        uid: str,
        pin_id: int | None,
    ) -> str:
        if kind == RateLimitKind.EDIT:
            if pin_id is None:
                raise ValueError("pin_id is required for EDIT rate limit")
            return str(pin_id)
        return uid

    @staticmethod
    def _policy(kind: RateLimitKind) -> tuple[bool, int]:
        if kind == RateLimitKind.AI:
            return (
                settings.ai_pin_generation_rate_limit_enabled,
                settings.ai_pin_generation_daily_limit,
            )
        if kind == RateLimitKind.CREATE:
            return (
                settings.issue_pin_create_rate_limit_enabled,
                settings.issue_pin_create_daily_limit,
            )
        return (
            settings.issue_pin_edit_rate_limit_enabled,
            settings.issue_pin_edit_daily_limit,
        )

    def _is_enforcement_active(self, kind: RateLimitKind) -> bool:
        enabled, daily_limit = self._policy(kind)
        return enabled and daily_limit >= 1

    def _disabled_quota_status(self, *, kind: RateLimitKind, reset_at: datetime) -> IssuePinQuotaStatus:
        _, daily_limit = self._policy(kind)
        return IssuePinQuotaStatus(
            enabled=False,
            daily_limit=daily_limit,
            used_count=0,
            reset_at=reset_at,
        )

    def _raise_quota_exceeded(
        self,
        *,
        kind: RateLimitKind,
        daily_limit: int,
        used_count: int,
        reset_at: datetime,
        pin_id: int | None = None,
    ) -> None:
        snapshot = RateLimitSnapshot(
            daily_limit=daily_limit,
            used_count=used_count,
            reset_at=reset_at,
        )
        extra: dict[str, Any] = snapshot.to_result_dict()
        if kind == RateLimitKind.EDIT and pin_id is not None:
            extra["pinId"] = pin_id
        raise_business_exception(
            _ERROR_CODE_BY_KIND[kind],
            **extra,
        )

    async def assert_daily_quota_available(
        self,
        kind: RateLimitKind,
        *,
        uid: str,
        pin_id: int | None = None,
    ) -> None:
        if not self._is_enforcement_active(kind):
            return

        if self._redis_client is None:
            logger.warning(
                "Issue pin rate limit skipped: Redis client unavailable kind=%s uid=%s",
                kind,
                uid,
            )
            return

        _, daily_limit = self._policy(kind)
        subject_id = self._resolve_subject_id(kind=kind, uid=uid, pin_id=pin_id)
        now_kst = datetime.now(_KST)
        key = self.daily_key(kind=kind, subject_id=subject_id, kst_date=now_kst)
        reset_at = self.next_kst_midnight(now=now_kst)

        try:
            raw = await self._redis_client.get(key)
            used_count = int(raw) if raw is not None else 0
        except Exception:
            logger.warning(
                "Issue pin rate limit skipped: Redis error kind=%s uid=%s",
                kind,
                uid,
                exc_info=True,
            )
            return

        if used_count >= daily_limit:
            self._raise_quota_exceeded(
                kind=kind,
                daily_limit=daily_limit,
                used_count=used_count,
                reset_at=reset_at,
                pin_id=pin_id,
            )

    async def record_daily_quota_success(
        self,
        kind: RateLimitKind,
        *,
        uid: str,
        pin_id: int | None = None,
    ) -> RateLimitSnapshot | None:
        if not self._is_enforcement_active(kind):
            return None

        _, daily_limit = self._policy(kind)
        if self._redis_client is None or self._record_success_script is None:
            logger.warning(
                "Issue pin success record skipped: Redis client unavailable kind=%s uid=%s",
                kind,
                uid,
            )
            return None

        subject_id = self._resolve_subject_id(kind=kind, uid=uid, pin_id=pin_id)
        now_kst = datetime.now(_KST)
        key = self.daily_key(kind=kind, subject_id=subject_id, kst_date=now_kst)
        ttl_seconds = self.seconds_until_kst_midnight(now=now_kst)
        reset_at = self.next_kst_midnight(now=now_kst)

        try:
            raw = await self._record_success_script(
                keys=[key],
                args=[ttl_seconds, daily_limit],
            )
            if raw is None or len(raw) < 2:
                raise ValueError(f"unexpected redis script result: {raw!r}")
            recorded = int(raw[0]) == 1
            used_count = int(raw[1])
        except Exception:
            logger.warning(
                "Issue pin success record skipped: Redis error kind=%s uid=%s",
                kind,
                uid,
                exc_info=True,
            )
            return None

        snapshot = RateLimitSnapshot(
            daily_limit=daily_limit,
            used_count=used_count,
            reset_at=reset_at,
        )
        if not recorded:
            logger.warning(
                "Issue pin success record skipped: concurrent quota race kind=%s subject=%s used=%d limit=%d",
                kind,
                subject_id,
                used_count,
                daily_limit,
            )
        return snapshot

    async def get_daily_quota_status(
        self,
        kind: RateLimitKind,
        *,
        uid: str,
        pin_id: int | None = None,
    ) -> IssuePinQuotaStatus:
        enabled, daily_limit = self._policy(kind)
        now_kst = datetime.now(_KST)
        reset_at = self.next_kst_midnight(now=now_kst)

        if not enabled or daily_limit < 1:
            return self._disabled_quota_status(kind=kind, reset_at=reset_at)

        if self._redis_client is None:
            logger.warning(
                "Issue pin quota read skipped: Redis client unavailable kind=%s uid=%s",
                kind,
                uid,
            )
            return self._disabled_quota_status(kind=kind, reset_at=reset_at)

        subject_id = self._resolve_subject_id(kind=kind, uid=uid, pin_id=pin_id)
        key = self.daily_key(kind=kind, subject_id=subject_id, kst_date=now_kst)
        used_count = 0
        try:
            raw = await self._redis_client.get(key)
            if raw is not None:
                used_count = int(raw)
        except Exception:
            logger.warning(
                "Issue pin quota read failed kind=%s uid=%s",
                kind,
                uid,
                exc_info=True,
            )

        return IssuePinQuotaStatus(
            enabled=True,
            daily_limit=daily_limit,
            used_count=used_count,
            reset_at=reset_at,
        )

    def quota_status_from_snapshot(self, snapshot: RateLimitSnapshot | None, *, kind: RateLimitKind) -> IssuePinQuotaStatus:
        if snapshot is not None:
            return IssuePinQuotaStatus(
                enabled=True,
                daily_limit=snapshot.daily_limit,
                used_count=snapshot.used_count,
                reset_at=snapshot.reset_at,
            )
        _, daily_limit = self._policy(kind)
        reset_at = self.next_kst_midnight()
        if not self._is_enforcement_active(kind):
            return self._disabled_quota_status(kind=kind, reset_at=reset_at)
        return IssuePinQuotaStatus(
            enabled=True,
            daily_limit=daily_limit,
            used_count=0,
            reset_at=reset_at,
        )
