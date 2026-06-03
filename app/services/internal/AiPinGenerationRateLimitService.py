from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis as AsyncRedis

from app.core.codes import ErrorCode
from app.core.config import settings
from app.core.exceptions import raise_business_exception

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_DAILY_KEY_PREFIX = "issue_pin:ai:daily"
_EXPIRE_BUFFER_SECONDS = 60 * 60

_CONSUME_DAILY_QUOTA_LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if n > tonumber(ARGV[2]) then
  return {0, n}
end
return {1, n}
"""


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
class AiPinGenerationQuotaStatus:
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


class AiPinGenerationRateLimitService:
    def __init__(self, *, redis_client: AsyncRedis | None = None) -> None:
        self._redis_client = redis_client
        self._consume_script = (
            redis_client.register_script(_CONSUME_DAILY_QUOTA_LUA)
            if redis_client is not None
            else None
        )

    @staticmethod
    def daily_key(*, uid: str, kst_date: datetime) -> str:
        return f"{_DAILY_KEY_PREFIX}:{uid}:{kst_date.strftime('%Y%m%d')}"

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

    async def consume_daily_quota(self, *, uid: str) -> RateLimitSnapshot | None:
        if not settings.ai_pin_generation_rate_limit_enabled:
            return None

        daily_limit = settings.ai_pin_generation_daily_limit
        if daily_limit < 1:
            return None

        if self._redis_client is None or self._consume_script is None:
            logger.warning(
                "AI pin generation rate limit skipped: Redis client unavailable uid=%s",
                uid,
            )
            return None

        now_kst = datetime.now(_KST)
        key = self.daily_key(uid=uid, kst_date=now_kst)
        ttl_seconds = self.seconds_until_kst_midnight(now=now_kst)
        reset_at = self.next_kst_midnight(now=now_kst)

        try:
            raw = await self._consume_script(
                keys=[key],
                args=[ttl_seconds, daily_limit],
            )
        except Exception:
            logger.warning(
                "AI pin generation rate limit skipped: Redis error uid=%s",
                uid,
                exc_info=True,
            )
            return None

        allowed = int(raw[0]) == 1
        used_count = int(raw[1])
        snapshot = RateLimitSnapshot(
            daily_limit=daily_limit,
            used_count=used_count,
            reset_at=reset_at,
        )
        if not allowed:
            raise_business_exception(
                ErrorCode.AI_PIN_GENERATION_RATE_LIMIT_EXCEEDED,
                **snapshot.to_result_dict(),
            )
        return snapshot

    async def get_daily_quota_status(self, *, uid: str) -> AiPinGenerationQuotaStatus:
        daily_limit = settings.ai_pin_generation_daily_limit
        now_kst = datetime.now(_KST)
        reset_at = self.next_kst_midnight(now=now_kst)

        if not settings.ai_pin_generation_rate_limit_enabled or daily_limit < 1:
            return AiPinGenerationQuotaStatus(
                enabled=False,
                daily_limit=daily_limit,
                used_count=0,
                reset_at=reset_at,
            )

        if self._redis_client is None:
            logger.warning(
                "AI pin generation quota read skipped: Redis client unavailable uid=%s",
                uid,
            )
            return AiPinGenerationQuotaStatus(
                enabled=False,
                daily_limit=daily_limit,
                used_count=0,
                reset_at=reset_at,
            )

        key = self.daily_key(uid=uid, kst_date=now_kst)
        used_count = 0
        try:
            raw = await self._redis_client.get(key)
            if raw is not None:
                used_count = int(raw)
        except Exception:
            logger.warning(
                "AI pin generation quota read failed uid=%s",
                uid,
                exc_info=True,
            )

        return AiPinGenerationQuotaStatus(
            enabled=True,
            daily_limit=daily_limit,
            used_count=used_count,
            reset_at=reset_at,
        )
