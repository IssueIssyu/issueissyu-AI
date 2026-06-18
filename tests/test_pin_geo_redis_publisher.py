from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from app.services.internal.map.PinGeoRedisPublisher import (
    GEO_KEY_ALL,
    GEO_KEY_PREFIX,
    PIN_INFO_KEY_PREFIX,
    PIN_INFO_TTL_SECONDS,
    PinGeoCacheItem,
    PinGeoRedisPublisher,
    _build_pin_info_json,
)


class PinGeoRedisPublisherConstantsTest(unittest.TestCase):
    def test_pin_info_ttl_matches_backend_duration_of_hours_48(self) -> None:
        self.assertEqual(PIN_INFO_TTL_SECONDS, 172_800)


class PinGeoRedisPublisherJsonTest(unittest.TestCase):
    def test_build_pin_info_json_uses_java_camel_case_fields(self) -> None:
        payload = json.loads(
            _build_pin_info_json(
                pin_id=123,
                pin_type="ISSUE",
                lat=37.5,
                lng=127.0,
                detail_address="상세주소",
                region="서울특별시",
                discount=None,
            ),
        )
        self.assertEqual(
            payload,
            {
                "pinId": 123,
                "pinType": "ISSUE",
                "latitude": 37.5,
                "longitude": 127.0,
                "pinDetailAddress": "상세주소",
                "pinLocation": "서울특별시",
                "discount": None,
            },
        )


class PinGeoRedisPublisherAddPinTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.redis = MagicMock()
        self.redis.geoadd = AsyncMock()
        self.redis.set = AsyncMock()
        self.publisher = PinGeoRedisPublisher(self.redis)

    async def test_add_pin_writes_geo_and_pin_info_with_backend_ttl(self) -> None:
        await self.publisher.add_pin(
            pin_id=42,
            pin_type="ISSUE",
            lat=37.5,
            lng=127.0,
            detail_address="주소",
            region="서울",
            discount=None,
        )

        self.redis.geoadd.assert_any_await(GEO_KEY_ALL, (127.0, 37.5, "42"))
        self.redis.geoadd.assert_any_await(f"{GEO_KEY_PREFIX}ISSUE", (127.0, 37.5, "42"))
        self.redis.set.assert_awaited_once()
        set_args, set_kwargs = self.redis.set.await_args
        self.assertEqual(set_args[0], f"{PIN_INFO_KEY_PREFIX}42")
        self.assertEqual(set_kwargs["ex"], 172_800)
        payload = json.loads(set_args[1])
        self.assertEqual(payload["pinId"], 42)
        self.assertEqual(payload["pinType"], "ISSUE")

    async def test_add_pin_swallows_redis_errors(self) -> None:
        self.redis.geoadd.side_effect = RuntimeError("redis down")

        await self.publisher.add_pin(
            pin_id=1,
            pin_type="FESTIVAL",
            lat=37.0,
            lng=127.0,
            detail_address="주소",
            region="서울",
        )


class PinGeoRedisPublisherBatchTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.redis = MagicMock()
        self.pipeline = MagicMock()
        self.pipeline.__aenter__ = AsyncMock(return_value=self.pipeline)
        self.pipeline.__aexit__ = AsyncMock(return_value=None)
        self.pipeline.geoadd = MagicMock()
        self.pipeline.set = MagicMock()
        self.pipeline.execute = AsyncMock(return_value=[])
        self.redis.pipeline = MagicMock(return_value=self.pipeline)
        self.publisher = PinGeoRedisPublisher(self.redis)

    async def test_add_pins_batch_uses_pipeline(self) -> None:
        items = [
            PinGeoCacheItem(
                pin_id=1,
                pin_type="FESTIVAL",
                lat=37.1,
                lng=127.1,
                detail_address="A",
                region="서울",
            ),
            PinGeoCacheItem(
                pin_id=2,
                pin_type="FESTIVAL",
                lat=37.2,
                lng=127.2,
                detail_address="B",
                region="부산",
            ),
        ]

        await self.publisher.add_pins_batch(items)

        self.redis.pipeline.assert_called_once_with(transaction=False)
        self.assertEqual(self.pipeline.geoadd.call_count, 4)
        self.assertEqual(self.pipeline.set.call_count, 2)
        self.pipeline.execute.assert_awaited_once()
        _, set_kwargs = self.pipeline.set.call_args_list[0]
        self.assertEqual(set_kwargs["ex"], 172_800)

    async def test_add_pins_batch_noop_for_empty_list(self) -> None:
        await self.publisher.add_pins_batch([])
        self.redis.pipeline.assert_not_called()


class PinGeoRedisPublisherRemovePinTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.redis = MagicMock()
        self.redis.zrem = AsyncMock()
        self.redis.delete = AsyncMock()
        self.publisher = PinGeoRedisPublisher(self.redis)

    async def test_remove_pin_deletes_geo_and_info_keys(self) -> None:
        await self.publisher.remove_pin(pin_id=9, pin_type="ISSUE")

        self.redis.zrem.assert_any_await(GEO_KEY_ALL, "9")
        self.redis.zrem.assert_any_await(f"{GEO_KEY_PREFIX}ISSUE", "9")
        self.redis.delete.assert_awaited_once_with(f"{PIN_INFO_KEY_PREFIX}9")
