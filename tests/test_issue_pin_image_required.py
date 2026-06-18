from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException
from app.models.PinImage import PinImage
from app.schemas.IssueDTO import (
    CreateIssuePinMultipartRequest,
    PinImageIsMainItem,
    UpdateIssuePinMultipartRequest,
)
from app.services.IssueService import IssueService


def _build_issue_service() -> IssueService:
    return IssueService(
        vector_store_service=MagicMock(),
        issue_rag_planner_service=MagicMock(),
        location_resolve_client=MagicMock(),
        issue_pin_llm_service=MagicMock(),
        pin_repo=MagicMock(),
        issue_pin_repo=MagicMock(),
        pin_location_repo=MagicMock(),
        pin_image_repo=MagicMock(),
        pin_like_repo=MagicMock(),
        community_repo=MagicMock(),
        user_repo=MagicMock(),
        s3_util=MagicMock(),
        background_runner=MagicMock(),
        issue_pin_daily_rate_limit_service=MagicMock(),
        location_repo=MagicMock(),
        pin_geo_redis_publisher=MagicMock(),
    )


class IssuePinImageRequiredCreateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.service = _build_issue_service()
        self.service._rate_limit.assert_daily_quota_available = AsyncMock()

    async def test_create_raises_when_no_photos(self) -> None:
        request = CreateIssuePinMultipartRequest(
            lat=37.566535,
            lng=126.977969,
            pin_title="제목",
            pin_content="본문",
            pin_images=[PinImageIsMainItem(is_main=True)],
        )

        with self.assertRaises(BusinessException) as ctx:
            await self.service.create_issue_pin(
                uid="user-1",
                request=request,
                photos=[],
            )

        self.assertEqual(ctx.exception.error_code, ErrorCode.PIN_IMAGE_REQUIRED)

    async def test_create_raises_when_pin_images_empty(self) -> None:
        with self.assertRaises(ValueError):
            CreateIssuePinMultipartRequest(
                lat=37.566535,
                lng=126.977969,
                pin_title="제목",
                pin_content="본문",
                pin_images=[],
            )


class IssuePinImageRequiredUpdatePlanTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.service = _build_issue_service()

    async def test_update_plan_raises_when_all_images_removed(self) -> None:
        existing = PinImage(
            pin_image_id=1,
            pin_id=10,
            pin_s3_key="issueimage/a.jpg",
            pin_s3_url="https://example.com/a.jpg",
            is_main=True,
        )
        request = UpdateIssuePinMultipartRequest(
            pin_title="제목",
            pin_content="본문",
            pin_image_urls=[],
        )

        with self.assertRaises(BusinessException) as ctx:
            await self.service._build_update_pin_image_plan(
                pin_id=10,
                existing_images=[existing],
                request=request,
                photos=[],
            )

        self.assertEqual(ctx.exception.error_code, ErrorCode.PIN_IMAGE_REQUIRED)

    async def test_update_plan_allows_unchanged_when_existing_has_images(self) -> None:
        existing = PinImage(
            pin_image_id=1,
            pin_id=10,
            pin_s3_key="issueimage/a.jpg",
            pin_s3_url="https://example.com/a.jpg",
            is_main=True,
        )
        request = UpdateIssuePinMultipartRequest(
            pin_title="제목",
            pin_content="본문",
        )

        plan = await self.service._build_update_pin_image_plan(
            pin_id=10,
            existing_images=[existing],
            request=request,
            photos=[],
        )

        self.assertTrue(plan.images_unchanged)

    async def test_update_raises_when_unchanged_and_no_existing_images(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from app.models.IssuePin import IssuePin
        from app.models.Pin import Pin
        from app.models.PinLocation import PinLocation
        from app.models.enum.IssuePinState import IssuePinState
        from app.models.enum.PinType import PinType
        from app.models.enum.ToneType import ToneType

        pin = Pin(
            pin_id=10,
            uid="user-1",
            pin_type=PinType.ISSUE,
            pin_title="제목",
            pin_content="본문",
            tone_type=ToneType.NONE,
            like_count=0,
            view_count=0,
            created_at=datetime.now(tz=ZoneInfo("UTC")),
        )
        issue_pin = IssuePin(
            issue_pin_id=1,
            issue_pin_state=IssuePinState.BEFORE_PROGRESS,
            petition_count=0,
            pin_id=10,
            pin=pin,
        )
        pin_location = PinLocation(
            pin_id=10,
            location_id=1,
            detail_address="서울",
            pin_point="POINT(126.977969 37.566535)",
        )
        pin.pin_location = pin_location
        pin.pin_images = []

        self.service._user_repo.get_by_uid = AsyncMock(return_value=MagicMock(nickname="nick"))
        self.service._issue_pin_repo.get_by_pin_id = AsyncMock(return_value=issue_pin)
        self.service._rate_limit.assert_daily_quota_available = AsyncMock()

        request = UpdateIssuePinMultipartRequest(
            pin_title="수정 제목",
            pin_content="수정 본문",
        )

        with self.assertRaises(BusinessException) as ctx:
            await self.service.update_issue_pin(
                uid="user-1",
                pin_id=10,
                request=request,
                photos=[],
            )

        self.assertEqual(ctx.exception.error_code, ErrorCode.PIN_IMAGE_REQUIRED)


if __name__ == "__main__":
    unittest.main()
