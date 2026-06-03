from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException
from app.services.internal.AiPinGenerationRateLimitService import AiPinGenerationRateLimitService

_KST = ZoneInfo("Asia/Seoul")


class AiPinGenerationRateLimitHelpersTest(unittest.TestCase):
    def test_daily_key_uses_kst_date_suffix(self) -> None:
        kst_date = datetime(2026, 6, 3, 15, 30, tzinfo=_KST)
        key = AiPinGenerationRateLimitService.daily_key(uid="user-1", kst_date=kst_date)
        self.assertEqual(key, "issue_pin:ai:daily:user-1:20260603")

    def test_seconds_until_kst_midnight_includes_buffer(self) -> None:
        now = datetime(2026, 6, 3, 23, 0, 0, tzinfo=_KST)
        seconds = AiPinGenerationRateLimitService.seconds_until_kst_midnight(now=now)
        self.assertEqual(seconds, 3600 + 3600)

    def test_next_kst_midnight(self) -> None:
        now = datetime(2026, 6, 3, 15, 0, 0, tzinfo=_KST)
        reset_at = AiPinGenerationRateLimitService.next_kst_midnight(now=now)
        self.assertEqual(reset_at, datetime(2026, 6, 4, 0, 0, 0, tzinfo=_KST))


class AiPinGenerationRateLimitServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.redis_client = MagicMock()
        self.consume_script = AsyncMock()
        self.redis_client.register_script.return_value = self.consume_script
        self.service = AiPinGenerationRateLimitService(redis_client=self.redis_client)

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_consume_allows_up_to_daily_limit(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 3

        for used in range(1, 4):
            self.consume_script.return_value = [1, used]
            snapshot = await self.service.consume_daily_quota(uid="user-1")
            assert snapshot is not None
            self.assertEqual(snapshot.used_count, used)
            self.assertEqual(snapshot.daily_limit, 3)

        self.assertEqual(self.consume_script.await_count, 3)

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_consume_raises_when_limit_exceeded(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 10
        self.consume_script.return_value = [0, 11]

        with self.assertRaises(BusinessException) as ctx:
            await self.service.consume_daily_quota(uid="user-1")

        exc = ctx.exception
        self.assertEqual(exc.error_code, ErrorCode.AI_PIN_GENERATION_RATE_LIMIT_EXCEEDED)
        self.assertEqual(exc.extra["dailyLimit"], 10)
        self.assertEqual(exc.extra["usedCount"], 11)
        self.assertIn("resetAt", exc.extra)

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_consume_skips_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = False

        result = await self.service.consume_daily_quota(uid="user-1")

        self.assertIsNone(result)
        self.consume_script.assert_not_awaited()

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_consume_skips_when_redis_unavailable(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 10
        service = AiPinGenerationRateLimitService(redis_client=None)

        result = await service.consume_daily_quota(uid="user-1")

        self.assertIsNone(result)

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_consume_skips_on_redis_error(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 10
        self.consume_script.side_effect = RuntimeError("redis down")

        result = await self.service.consume_daily_quota(uid="user-1")

        self.assertIsNone(result)

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_consume_passes_key_ttl_and_limit_to_script(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 10
        self.consume_script.return_value = [1, 1]
        fixed_now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=_KST)

        with patch(
            "app.services.internal.AiPinGenerationRateLimitService.datetime",
        ) as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            await self.service.consume_daily_quota(uid="user-42")

        self.consume_script.assert_awaited_once()
        call_kwargs = self.consume_script.await_args.kwargs
        self.assertEqual(call_kwargs["keys"], ["issue_pin:ai:daily:user-42:20260603"])
        self.assertEqual(call_kwargs["args"][1], 10)
        self.assertGreater(call_kwargs["args"][0], 0)

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_get_quota_when_enabled(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 10
        self.redis_client.get = AsyncMock(return_value="3")

        quota = await self.service.get_daily_quota_status(uid="user-1")

        self.assertTrue(quota.enabled)
        self.assertEqual(quota.used_count, 3)
        self.assertEqual(quota.remaining_count, 7)
        self.assertEqual(quota.to_result_dict()["remainingCount"], 7)

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_get_quota_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = False
        mock_settings.ai_pin_generation_daily_limit = 10

        quota = await self.service.get_daily_quota_status(uid="user-1")

        self.assertFalse(quota.enabled)
        self.assertEqual(quota.used_count, 0)
        self.assertEqual(quota.remaining_count, 10)
        self.redis_client.get.assert_not_called()

    @patch("app.services.internal.AiPinGenerationRateLimitService.settings")
    async def test_get_quota_when_redis_unavailable(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 10
        service = AiPinGenerationRateLimitService(redis_client=None)

        quota = await service.get_daily_quota_status(uid="user-1")

        self.assertFalse(quota.enabled)
        self.assertEqual(quota.remaining_count, 10)


if __name__ == "__main__":
    unittest.main()
