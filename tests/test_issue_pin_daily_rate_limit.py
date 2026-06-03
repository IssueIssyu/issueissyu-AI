from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException
from app.services.internal.IssuePinDailyRateLimitService import (
    IssuePinDailyRateLimitService,
    RateLimitKind,
)

_KST = ZoneInfo("Asia/Seoul")


class IssuePinDailyRateLimitHelpersTest(unittest.TestCase):
    def test_daily_key_ai_uses_uid(self) -> None:
        kst_date = datetime(2026, 6, 3, 15, 30, tzinfo=_KST)
        key = IssuePinDailyRateLimitService.daily_key(
            kind=RateLimitKind.AI,
            subject_id="user-1",
            kst_date=kst_date,
        )
        self.assertEqual(key, "issue_pin:ai:daily:user-1:20260603")

    def test_daily_key_edit_uses_pin_id(self) -> None:
        kst_date = datetime(2026, 6, 3, 15, 30, tzinfo=_KST)
        key = IssuePinDailyRateLimitService.daily_key(
            kind=RateLimitKind.EDIT,
            subject_id="42",
            kst_date=kst_date,
        )
        self.assertEqual(key, "issue_pin:edit:daily:42:20260603")

    def test_daily_key_create_uses_uid(self) -> None:
        kst_date = datetime(2026, 6, 3, 15, 30, tzinfo=_KST)
        key = IssuePinDailyRateLimitService.daily_key(
            kind=RateLimitKind.CREATE,
            subject_id="user-1",
            kst_date=kst_date,
        )
        self.assertEqual(key, "issue_pin:create:daily:user-1:20260603")

    def test_seconds_until_kst_midnight_includes_buffer(self) -> None:
        now = datetime(2026, 6, 3, 23, 0, 0, tzinfo=_KST)
        seconds = IssuePinDailyRateLimitService.seconds_until_kst_midnight(now=now)
        self.assertEqual(seconds, 3600 + 3600)

    def test_next_kst_midnight(self) -> None:
        now = datetime(2026, 6, 3, 15, 0, 0, tzinfo=_KST)
        reset_at = IssuePinDailyRateLimitService.next_kst_midnight(now=now)
        self.assertEqual(reset_at, datetime(2026, 6, 4, 0, 0, 0, tzinfo=_KST))


class IssuePinDailyRateLimitServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.redis_client = MagicMock()
        self.record_script = AsyncMock()
        self.redis_client.register_script.return_value = self.record_script
        self.redis_client.get = AsyncMock(return_value=None)
        self.service = IssuePinDailyRateLimitService(redis_client=self.redis_client)

    @patch("app.services.internal.IssuePinDailyRateLimitService.settings")
    async def test_assert_ai_allows_when_under_daily_limit(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 10
        self.redis_client.get.return_value = "9"

        await self.service.assert_daily_quota_available(RateLimitKind.AI, uid="user-1")

        self.redis_client.get.assert_awaited_once()

    @patch("app.services.internal.IssuePinDailyRateLimitService.settings")
    async def test_assert_create_raises_without_increment(self, mock_settings: MagicMock) -> None:
        mock_settings.issue_pin_create_rate_limit_enabled = True
        mock_settings.issue_pin_create_daily_limit = 10
        self.redis_client.get.return_value = "10"

        with self.assertRaises(BusinessException) as ctx:
            await self.service.assert_daily_quota_available(RateLimitKind.CREATE, uid="user-1")

        exc = ctx.exception
        self.assertEqual(exc.error_code, ErrorCode.ISSUE_PIN_CREATE_RATE_LIMIT_EXCEEDED)
        self.record_script.assert_not_awaited()

    @patch("app.services.internal.IssuePinDailyRateLimitService.settings")
    async def test_assert_edit_raises_with_pin_id(self, mock_settings: MagicMock) -> None:
        mock_settings.issue_pin_edit_rate_limit_enabled = True
        mock_settings.issue_pin_edit_daily_limit = 3
        self.redis_client.get.return_value = "3"

        with self.assertRaises(BusinessException) as ctx:
            await self.service.assert_daily_quota_available(
                RateLimitKind.EDIT,
                uid="user-1",
                pin_id=99,
            )

        exc = ctx.exception
        self.assertEqual(exc.error_code, ErrorCode.ISSUE_PIN_EDIT_RATE_LIMIT_EXCEEDED)
        self.assertEqual(exc.extra["pinId"], 99)

    @patch("app.services.internal.IssuePinDailyRateLimitService.settings")
    async def test_record_edit_increments_pin_key(self, mock_settings: MagicMock) -> None:
        mock_settings.issue_pin_edit_rate_limit_enabled = True
        mock_settings.issue_pin_edit_daily_limit = 5
        self.record_script.return_value = [1, 2]
        fixed_now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=_KST)

        with patch(
            "app.services.internal.IssuePinDailyRateLimitService.datetime",
        ) as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            snapshot = await self.service.record_daily_quota_success(
                RateLimitKind.EDIT,
                uid="user-1",
                pin_id=77,
            )

        assert snapshot is not None
        self.assertEqual(snapshot.used_count, 2)
        call_kwargs = self.record_script.await_args.kwargs
        self.assertEqual(call_kwargs["keys"], ["issue_pin:edit:daily:77:20260603"])

    @patch("app.services.internal.IssuePinDailyRateLimitService.settings")
    async def test_record_skips_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.issue_pin_create_rate_limit_enabled = False

        result = await self.service.record_daily_quota_success(RateLimitKind.CREATE, uid="user-1")

        self.assertIsNone(result)
        self.record_script.assert_not_awaited()

    @patch("app.services.internal.IssuePinDailyRateLimitService.settings")
    async def test_get_quota_create_when_enabled(self, mock_settings: MagicMock) -> None:
        mock_settings.issue_pin_create_rate_limit_enabled = True
        mock_settings.issue_pin_create_daily_limit = 10
        self.redis_client.get = AsyncMock(return_value="4")

        quota = await self.service.get_daily_quota_status(RateLimitKind.CREATE, uid="user-1")

        self.assertTrue(quota.enabled)
        self.assertEqual(quota.remaining_count, 6)
        self.assertEqual(quota.to_result_dict()["remainingCount"], 6)

    @patch("app.services.internal.IssuePinDailyRateLimitService.settings")
    async def test_get_quota_edit_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.issue_pin_edit_rate_limit_enabled = False
        mock_settings.issue_pin_edit_daily_limit = 10

        quota = await self.service.get_daily_quota_status(
            RateLimitKind.EDIT,
            uid="user-1",
            pin_id=1,
        )

        self.assertFalse(quota.enabled)
        self.assertEqual(quota.remaining_count, 10)

    @patch("app.services.internal.IssuePinDailyRateLimitService.settings")
    async def test_quota_status_from_snapshot(self, mock_settings: MagicMock) -> None:
        mock_settings.ai_pin_generation_rate_limit_enabled = True
        mock_settings.ai_pin_generation_daily_limit = 10
        reset_at = datetime(2026, 6, 4, 0, 0, 0, tzinfo=_KST)
        from app.services.internal.IssuePinDailyRateLimitService import RateLimitSnapshot

        snapshot = RateLimitSnapshot(daily_limit=10, used_count=3, reset_at=reset_at)
        status = self.service.quota_status_from_snapshot(snapshot, kind=RateLimitKind.AI)

        self.assertEqual(status.remaining_count, 7)
        self.assertEqual(status.to_result_dict()["remainingCount"], 7)


if __name__ == "__main__":
    unittest.main()
