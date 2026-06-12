from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import app.models  # noqa: F401 — SQLAlchemy mapper registry

from app.schemas.PolicyAdminDTO import (
    PolicyBatchAction,
    PolicyBatchItemResult,
    PolicyImportBatchResult,
)
from app.schemas.PolicyPinDTO import PolicyPinSearchResult, PolicyPinTransformResult
from app.services.PolicyEventIngestService import PolicyEventIngestService
from app.services.PolicyPinService import PolicyPinService
from app.services.internal.PolicyPinSchedulerService import PolicyPinSchedulerService
from app.services.policy_cardnews import _upload_local_handoff_path

_KST = ZoneInfo("Asia/Seoul")


def _make_ingest_service() -> PolicyEventIngestService:
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    pin_repo = MagicMock()
    pin_repo.session = session
    pin_repo.commit = AsyncMock()
    pin_repo.rollback = AsyncMock()
    event_pin_repo = MagicMock()
    event_pin_repo.list_policy_api_ids = AsyncMock(return_value=set())
    event_pin_repo.get_by_policy_api_id = AsyncMock(return_value=None)
    event_pin_repo.save = AsyncMock()
    community_repo = MagicMock()
    community_repo.save = AsyncMock()
    cardnews_repo = MagicMock()
    cardnews_repo.save = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_by_user_name = AsyncMock(return_value=MagicMock(uid="admin-uid"))
    return PolicyEventIngestService(
        pin_repo=pin_repo,
        event_pin_repo=event_pin_repo,
        community_repo=community_repo,
        cardnews_image_s3_repo=cardnews_repo,
        user_repo=user_repo,
    )


class PolicyPinSchedulerShouldRunSyncTest(unittest.TestCase):
    def test_runs_when_elapsed_within_one_hour_of_interval(self) -> None:
        scheduler = PolicyPinSchedulerService(s3_util=MagicMock())
        last_sync = datetime(2026, 6, 9, 1, 0, 5, tzinfo=_KST)
        now = datetime(2026, 6, 12, 1, 0, 0, tzinfo=_KST)

        with (
            patch(
                "app.services.internal.PolicyPinSchedulerService.POLICY_SYNC_META_PATH",
                MagicMock(is_file=MagicMock(return_value=True)),
            ),
            patch(
                "app.services.internal.PolicyPinSchedulerService.json.loads",
                return_value={"last_sync_at": last_sync.isoformat()},
            ),
            patch(
                "app.services.internal.PolicyPinSchedulerService.datetime") as mock_dt,
            patch(
                "app.services.internal.PolicyPinSchedulerService.settings.policy_sync_interval_days",
                3,
            ),
        ):
            mock_dt.now.return_value = now
            mock_dt.fromisoformat = datetime.fromisoformat
            self.assertTrue(scheduler._should_run_sync())

    def test_skips_when_elapsed_more_than_one_hour_short_of_interval(self) -> None:
        scheduler = PolicyPinSchedulerService(s3_util=MagicMock())
        last_sync = datetime(2026, 6, 9, 1, 0, 5, tzinfo=_KST)
        now = datetime(2026, 6, 11, 23, 0, 0, tzinfo=_KST)

        with (
            patch(
                "app.services.internal.PolicyPinSchedulerService.POLICY_SYNC_META_PATH",
                MagicMock(is_file=MagicMock(return_value=True)),
            ),
            patch(
                "app.services.internal.PolicyPinSchedulerService.json.loads",
                return_value={"last_sync_at": last_sync.isoformat()},
            ),
            patch(
                "app.services.internal.PolicyPinSchedulerService.datetime") as mock_dt,
            patch(
                "app.services.internal.PolicyPinSchedulerService.settings.policy_sync_interval_days",
                3,
            ),
        ):
            mock_dt.now.return_value = now
            mock_dt.fromisoformat = datetime.fromisoformat
            self.assertFalse(scheduler._should_run_sync())


class PolicyCardnewsHandoffPathTest(unittest.IsolatedAsyncioTestCase):
    async def test_upload_local_handoff_path_accepts_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            slide_path = Path(tmp) / "slide_01.png"
            slide_path.write_bytes(b"png-bytes")
            s3_util = MagicMock()
            s3_util.upload_bytes = AsyncMock(
                return_value={"key": "policy/cardnews/1/slide_01.png", "url": "https://cdn.example/slide_01.png"},
            )

            result = await _upload_local_handoff_path(
                s3_util,
                content_id="1",
                handoff_path=str(slide_path),
            )

            self.assertEqual(result["key"], "policy/cardnews/1/slide_01.png")
            s3_util.upload_bytes.assert_awaited_once()


class PolicyImportHandoffBatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_requested_batch_size_none_when_import_all(self) -> None:
        service = _make_ingest_service()
        handoff_rows = [
            {
                "contentid": "1",
                "policy_api_id": 1,
                "title": "정책1",
                "pin_content": "본문1",
                "cardnews_images": [{"key": "k1", "url": "https://cdn.example/1.png"}],
            },
        ]
        with (
            patch(
                "app.services.PolicyEventIngestService.load_jsonl_rows",
                return_value=handoff_rows,
            ),
            patch(
                "app.services.PolicyEventIngestService.settings.policy_prune_pipeline_after_import",
                False,
            ),
            patch.object(service, "_insert_policy_pin", AsyncMock(return_value=101)),
        ):
            result = await service.import_handoff_batch(import_all=True, limit=5)

        self.assertIsNone(result.requested_batch_size)
        self.assertEqual(result.inserted_count, 1)

    async def test_requested_batch_size_limit_when_not_import_all(self) -> None:
        service = _make_ingest_service()
        handoff_rows = [
            {
                "contentid": "1",
                "policy_api_id": 1,
                "title": "정책1",
                "pin_content": "본문1",
                "cardnews_images": [{"key": "k1", "url": "https://cdn.example/1.png"}],
            },
        ]
        with (
            patch(
                "app.services.PolicyEventIngestService.load_jsonl_rows",
                return_value=handoff_rows,
            ),
            patch(
                "app.services.PolicyEventIngestService.settings.policy_prune_pipeline_after_import",
                False,
            ),
            patch.object(service, "_insert_policy_pin", AsyncMock(return_value=101)),
        ):
            result = await service.import_handoff_batch(import_all=False, limit=3)

        self.assertEqual(result.requested_batch_size, 3)


class PolicySyncPipelineAccumulationTest(unittest.IsolatedAsyncioTestCase):
    async def test_import_results_accumulate_across_batches(self) -> None:
        service = PolicyPinService()
        ingest = _make_ingest_service()
        ingest._event_pin_repo.list_policy_api_ids = AsyncMock(return_value=set())

        transform_batches = [
            PolicyPinTransformResult(
                input_path="in.jsonl",
                output_path="out.jsonl",
                processed_count=2,
                error_count=0,
                pins=[],
                pending_count=1,
            ),
            PolicyPinTransformResult(
                input_path="in.jsonl",
                output_path="out.jsonl",
                processed_count=1,
                error_count=0,
                pins=[],
                pending_count=0,
            ),
        ]
        import_batches = [
            PolicyImportBatchResult(
                inserted_count=2,
                skipped_duplicate_count=0,
                pending_import_count=1,
                error_count=1,
                errors=[{"policy_api_id": 1, "error": "e1"}],
                items=[
                    PolicyBatchItemResult(policy_api_id=1, action=PolicyBatchAction.CREATED),
                    PolicyBatchItemResult(policy_api_id=2, action=PolicyBatchAction.ERROR, message="e1"),
                ],
                pin_ids=[11, 12],
            ),
            PolicyImportBatchResult(
                inserted_count=1,
                skipped_duplicate_count=0,
                pending_import_count=0,
                error_count=0,
                errors=[],
                items=[PolicyBatchItemResult(policy_api_id=3, action=PolicyBatchAction.CREATED)],
                pin_ids=[13],
            ),
        ]

        with (
            patch(
                "app.services.PolicyPinService.settings.policy_prune_pipeline_after_import",
                False,
            ),
            patch.object(
                service,
                "search_and_save",
                AsyncMock(
                    return_value=PolicyPinSearchResult(
                        query_start_date="20260610",
                        query_end_date="20260612",
                        count=0,
                        pins=[],
                        saved_documents_path="docs.jsonl",
                        stats={},
                    ),
                ),
            ),
            patch.object(service, "transform_and_save", AsyncMock(side_effect=transform_batches)),
            patch.object(ingest, "import_handoff_batch", AsyncMock(side_effect=import_batches)),
            patch.object(PolicyEventIngestService, "write_sync_meta"),
        ):
            result = await service.sync_pipeline(
                ingest_service=ingest,
                s3_util=MagicMock(),
                start_date="20260610",
                end_date="20260612",
                batch_size=2,
            )

        import_result = result.import_result
        self.assertEqual(import_result.inserted_count, 3)
        self.assertEqual(import_result.error_count, 1)
        self.assertEqual(len(import_result.items), 3)
        self.assertEqual(import_result.pin_ids, [11, 12, 13])
        self.assertEqual(import_result.errors, [{"policy_api_id": 1, "error": "e1"}])


if __name__ == "__main__":
    unittest.main()
