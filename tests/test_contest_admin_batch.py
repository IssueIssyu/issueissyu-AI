from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import app.models  # noqa: F401 — SQLAlchemy mapper registry

from app.models.enum.PinType import PinType
from app.schemas.ContestAdminDTO import ContestBatchAction
from app.services.ContestEventIngestService import ContestEventIngestService
from app.services.contest_pin_transform import (
    count_pending_transform,
    count_skipped_expired_transform_rows,
    list_pending_transform_rows,
    parse_contest_api_id,
)
from app.services.internal.ContestPinSchedulerService import ContestPinSchedulerService
from app.utils.contest_images import collect_contest_pin_image_specs, pin_images_for_db_row

_KST = ZoneInfo("Asia/Seoul")


class ContestImageSpecsTest(unittest.TestCase):
    def test_collect_contest_pin_image_specs_attachment_and_media_cdn(self) -> None:
        image_urls = [
            "https://api.linkareer.com/attachments/854194",
            "https://api.linkareer.com/attachments/852372",
            "https://media-cdn.linkareer.com//se2editor/image/852371",
        ]
        specs = collect_contest_pin_image_specs(image_urls)
        self.assertEqual(
            specs,
            [
                {"pin_image_url": image_urls[0], "is_main": True},
                {"pin_image_url": image_urls[2], "is_main": False},
            ],
        )
        db_specs = pin_images_for_db_row({"pin_images": specs})
        self.assertEqual(sum(1 for s in db_specs if s["is_main"]), 1)

    def test_parse_contest_api_id(self) -> None:
        self.assertEqual(parse_contest_api_id({"contentid": "319419"}), 319419)
        self.assertEqual(parse_contest_api_id({"contest_api_id": 42}), 42)
        self.assertIsNone(parse_contest_api_id({"contentid": "abc"}))


class ContestTransformPendingTest(unittest.TestCase):
    def test_list_pending_transform_rows_skips_db_and_handoff(self) -> None:
        documents = [
            {"contentid": "1", "pin_content_raw": "a"},
            {"contentid": "2", "pin_content_raw": "b"},
            {"contentid": "3", "pin_content_raw": "c"},
        ]
        handoff = {
            "2": {"contentid": "2", "pin_content": "done"},
        }
        pending = list_pending_transform_rows(
            documents,
            handoff,
            db_contest_api_ids={1},
        )
        self.assertEqual([row["contentid"] for row in pending], ["3"])
        self.assertEqual(
            count_pending_transform(documents, handoff, db_contest_api_ids={1}),
            1,
        )

    def test_list_pending_transform_rows_skips_expired(self) -> None:
        documents = [
            {"contentid": "1", "pin_content_raw": "a", "event_end_time": "20200101"},
            {"contentid": "2", "pin_content_raw": "b", "event_end_time": "20991231"},
        ]
        with patch(
            "app.services.contest_pin_transform.is_contest_row_expired",
            side_effect=lambda row: row.get("contentid") == "1",
        ):
            pending = list_pending_transform_rows(documents, {})
        self.assertEqual([row["contentid"] for row in pending], ["2"])
        self.assertEqual(
            count_skipped_expired_transform_rows(documents, {}),
            1,
        )


def _make_ingest_service() -> ContestEventIngestService:
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    pin_repo = MagicMock()
    pin_repo.session = session
    pin_repo.commit = AsyncMock()
    pin_repo.rollback = AsyncMock()
    pin_repo.save = AsyncMock(side_effect=lambda entity, **_: setattr(entity, "pin_id", 101))
    event_pin_repo = MagicMock()
    event_pin_repo.list_contest_api_ids = AsyncMock(return_value=set())
    event_pin_repo.save = AsyncMock()
    community_repo = MagicMock()
    community_repo.save = AsyncMock(side_effect=lambda entity, **_: setattr(entity, "community_id", 201))
    cardnews_repo = MagicMock()
    cardnews_repo.save = AsyncMock()
    pin_image_repo = MagicMock()
    pin_image_repo.save = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_by_user_name = AsyncMock(return_value=MagicMock(uid="admin-uid"))
    return ContestEventIngestService(
        pin_repo=pin_repo,
        event_pin_repo=event_pin_repo,
        community_repo=community_repo,
        cardnews_image_s3_repo=cardnews_repo,
        pin_image_repo=pin_image_repo,
        user_repo=user_repo,
    )


class ContestEventIngestServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_insert_contest_pin_uses_contest_types(self) -> None:
        service = _make_ingest_service()
        row = {
            "title": "공모전",
            "pin_content": "본문",
            "event_start_time": "20260101",
            "event_end_time": "20260201",
            "pin_images": [
                {"pin_image_url": "https://api.linkareer.com/attachments/1", "is_main": True},
                {"pin_image_url": "https://media-cdn.linkareer.com/a", "is_main": False},
            ],
            "cardnews_images": [{"key": "contest-cardnews/1/slide_01.png", "url": "https://s3.example/1.png"}],
        }
        pin_id = await service._insert_contest_pin(admin_uid="admin-uid", row=row, contest_api_id=319419)
        self.assertEqual(pin_id, 101)

        pin_entity = service._pin_repo.save.await_args_list[0].args[0]
        self.assertEqual(pin_entity.pin_type, PinType.CONTEST)

        community_entity = service._community_repo.save.await_args_list[0].args[0]
        self.assertEqual(community_entity.community_type, "CONTEST")

        event_pin_entity = service._event_pin_repo.save.await_args_list[0].args[0]
        self.assertEqual(event_pin_entity.contest_api_id, 319419)

        pin_image_calls = service._pin_image_repo.save.await_args_list
        self.assertEqual(len(pin_image_calls), 2)
        self.assertTrue(pin_image_calls[0].args[0].is_main)
        self.assertFalse(pin_image_calls[1].args[0].is_main)

        cardnews_entity = service._cardnews_image_s3_repo.save.await_args_list[0].args[0]
        self.assertEqual(cardnews_entity.community_id, 201)

    async def test_import_handoff_batch_skips_duplicate(self) -> None:
        service = _make_ingest_service()
        service._event_pin_repo.list_contest_api_ids = AsyncMock(return_value={100})

        with tempfile.TemporaryDirectory() as tmp:
            handoff_path = Path(tmp) / "contest_pins_for_db.jsonl"
            handoff_path.write_text(
                '{"contentid":"100","contest_api_id":100,"title":"A","pin_content":"B",'
                '"event_start_time":"20260101","event_end_time":"20261231",'
                '"pin_images":[],"cardnews_images":[]}\n',
                encoding="utf-8",
            )
            with unittest.mock.patch(
                "app.services.ContestEventIngestService.CONTEST_HANDOFF_PATH",
                handoff_path,
            ):
                result = await service.import_handoff_batch(import_all=True)

        self.assertEqual(result.inserted_count, 0)
        self.assertEqual(result.skipped_duplicate_count, 1)
        self.assertEqual(result.items[0].action, ContestBatchAction.SKIPPED)

    async def test_import_handoff_batch_skips_expired(self) -> None:
        service = _make_ingest_service()
        expired_end = (datetime.now(_KST).date().replace(year=2020)).strftime("%Y%m%d")

        with tempfile.TemporaryDirectory() as tmp:
            handoff_path = Path(tmp) / "contest_pins_for_db.jsonl"
            handoff_path.write_text(
                f'{{"contentid":"200","contest_api_id":200,"title":"Expired","pin_content":"B",'
                f'"event_start_time":"20200101","event_end_time":"{expired_end}",'
                f'"pin_images":[],"cardnews_images":[]}}\n',
                encoding="utf-8",
            )
            with unittest.mock.patch(
                "app.services.ContestEventIngestService.CONTEST_HANDOFF_PATH",
                handoff_path,
            ):
                result = await service.import_handoff_batch(import_all=True)

        self.assertEqual(result.inserted_count, 0)
        self.assertEqual(result.skipped_expired_count, 1)
        self.assertEqual(result.items[0].action, ContestBatchAction.SKIPPED)
        self.assertEqual(result.items[0].message, "종료일 경과")


class ContestPinSchedulerTest(unittest.TestCase):
    def test_seconds_until_next_schedule_kst_at_noon(self) -> None:
        scheduler = ContestPinSchedulerService(s3_util=MagicMock())
        now = datetime(2026, 6, 13, 10, 0, 0, tzinfo=_KST)

        with unittest.mock.patch(
            "app.services.internal.ContestPinSchedulerService.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            seconds = scheduler._seconds_until_next_schedule_kst()

        self.assertAlmostEqual(seconds, 2 * 60 * 60, delta=1.0)


if __name__ == "__main__":
    unittest.main()
