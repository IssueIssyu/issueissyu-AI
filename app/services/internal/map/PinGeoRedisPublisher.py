from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)

# BE PinGeoRedisService 와 동일
GEO_KEY_ALL = "geo:pins"
GEO_KEY_PREFIX = "geo:pins:"
PIN_INFO_KEY_PREFIX = "pin:info:"
PIN_INFO_TTL = timedelta(hours=48)
PIN_INFO_TTL_SECONDS = int(PIN_INFO_TTL.total_seconds())


@dataclass(frozen=True, slots=True)
class PinGeoCacheItem:
    pin_id: int
    pin_type: str
    lat: float
    lng: float
    detail_address: str
    region: str
    discount: str | None = None


class PinGeoRedisPublisher:
    """BE PinGeoRedisService write 규약을 미러링하는 Redis GEO 캐시 발행기."""

    def __init__(self, redis_client: AsyncRedis) -> None:
        self._redis = redis_client

    async def add_pin(
        self,
        *,
        pin_id: int,
        pin_type: str,
        lat: float,
        lng: float,
        detail_address: str,
        region: str,
        discount: str | None = None,
    ) -> None:
        try:
            member = str(pin_id)
            await self._redis.geoadd(GEO_KEY_ALL, (lng, lat, member))
            await self._redis.geoadd(f"{GEO_KEY_PREFIX}{pin_type}", (lng, lat, member))
            payload = _build_pin_info_json(
                pin_id=pin_id,
                pin_type=pin_type,
                lat=lat,
                lng=lng,
                detail_address=detail_address,
                region=region,
                discount=discount,
            )
            await self._redis.set(
                f"{PIN_INFO_KEY_PREFIX}{pin_id}",
                payload,
                ex=PIN_INFO_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("Redis GEO 핀 추가 실패 pin_id=%s: %s", pin_id, exc)

    async def add_pins_batch(self, items: list[PinGeoCacheItem]) -> None:
        if not items:
            return
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for item in items:
                    member = str(item.pin_id)
                    pipe.geoadd(GEO_KEY_ALL, (item.lng, item.lat, member))
                    pipe.geoadd(f"{GEO_KEY_PREFIX}{item.pin_type}", (item.lng, item.lat, member))
                    pipe.set(
                        f"{PIN_INFO_KEY_PREFIX}{item.pin_id}",
                        _build_pin_info_json(
                            pin_id=item.pin_id,
                            pin_type=item.pin_type,
                            lat=item.lat,
                            lng=item.lng,
                            detail_address=item.detail_address,
                            region=item.region,
                            discount=item.discount,
                        ),
                        ex=PIN_INFO_TTL_SECONDS,
                    )
                await pipe.execute()
        except Exception as exc:
            logger.warning("Redis GEO 핀 batch 추가 실패 count=%s: %s", len(items), exc)

    async def remove_pin(self, *, pin_id: int, pin_type: str) -> None:
        try:
            member = str(pin_id)
            await self._redis.zrem(GEO_KEY_ALL, member)
            await self._redis.zrem(f"{GEO_KEY_PREFIX}{pin_type}", member)
            await self._redis.delete(f"{PIN_INFO_KEY_PREFIX}{pin_id}")
        except Exception as exc:
            logger.warning("Redis GEO 핀 삭제 실패 pin_id=%s: %s", pin_id, exc)


def _build_pin_info_json(
    *,
    pin_id: int,
    pin_type: str,
    lat: float,
    lng: float,
    detail_address: str,
    region: str,
    discount: str | None,
) -> str:
    payload: dict[str, Any] = {
        "pinId": pin_id,
        "pinType": pin_type,
        "latitude": lat,
        "longitude": lng,
        "pinDetailAddress": detail_address,
        "pinLocation": region,
        "discount": discount,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
