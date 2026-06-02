from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import app.models  # noqa: F401 — SQLAlchemy mapper registry

from app.schemas.FestivalAdminDTO import FestivalImportBatchResult
from app.services.FestivalEventIngestService import FestivalEventIngestService, _parse_event_datetime
from app.services.festival_pin_transform import (
    build_handoff_row,
    count_pending_transform,
    list_pending_transform_rows,
    needs_llm_transform,
    normalize_raw_for_compare,
    parse_festival_api_id,
    reuse_transformed_row_if_unchanged,
    transform_documents_batch,
)
from app.utils.festival_date_filter import current_year_festival_range
from app.utils.visitkorea_area import (
    infer_area_code_from_addr,
    resolve_row_area_code,
    row_matches_area_filter,
    validate_area_code,
    validate_sigungu_code,
)
from app.utils.visitkorea_facilities import extract_pet_friendly


class FestivalTransformHelpersTest(unittest.TestCase):
    def test_parse_festival_api_id(self) -> None:
        self.assertEqual(parse_festival_api_id({"contentid": "12345"}), 12345)
        self.assertEqual(parse_festival_api_id({"festival_api_id": 99}), 99)
        self.assertIsNone(parse_festival_api_id({"contentid": "abc"}))

    def test_normalize_raw_for_compare(self) -> None:
        self.assertEqual(
            normalize_raw_for_compare("hello\n\nworld"),
            "hello world",
        )

    def test_reuse_transformed_row_if_unchanged(self) -> None:
        source = {
            "contentid": "1",
            "pin_title": "축제",
            "pin_content": "원문 텍스트",
        }
        existing = {
            "contentid": "1",
            "festival_api_id": 1,
            "pin_title": "가공 제목",
            "pin_content_raw": "원문 텍스트",
            "pin_content": "가공 본문",
        }
        reused = reuse_transformed_row_if_unchanged(source_row=source, existing_row=existing)
        self.assertIsNotNone(reused)
        assert reused is not None
        self.assertEqual(reused["pin_content"], "가공 본문")
        self.assertEqual(reused["festival_api_id"], 1)

    def test_needs_llm_when_raw_changed(self) -> None:
        source = {"contentid": "1", "pin_content": "새 원문"}
        existing = {
            "pin_content_raw": "옛 원문",
            "pin_content": "본문",
            "pin_title": "제목",
        }
        self.assertTrue(needs_llm_transform(source, existing))

    def test_build_handoff_row_includes_festival_api_id(self) -> None:
        row = build_handoff_row(
            {
                "contentid": "42",
                "pin_title": "원제목",
                "addr": "서울",
                "pin_images": [{"pin_image_url": "https://example.com/main.jpg", "is_main": True}],
            },
            pin_title="LLM 제목",
            pin_content="LLM 본문",
        )
        self.assertEqual(row["festival_api_id"], 42)
        self.assertEqual(row["pin_title"], "LLM 제목")
        self.assertEqual(row["pin_images"][0]["is_main"], True)

    def test_collect_pin_image_specs_uses_firstimage_only(self) -> None:
        from rag.scripts.fetch_visitkorea import collect_pin_image_specs, pin_images_for_db_row

        list_item = {
            "firstimage": "https://example.com/main.jpg",
            "firstimage2": "https://example.com/thumb.jpg",
        }
        image_payload = {
            "response": {
                "body": {
                    "items": {
                        "item": [
                            {"originimgurl": "https://example.com/gallery.jpg"},
                        ],
                    },
                },
            },
        }
        specs = collect_pin_image_specs(list_item, None, image_payload)
        self.assertEqual(
            specs,
            [
                {"pin_image_url": "https://example.com/main.jpg", "is_main": True},
                {"pin_image_url": "https://example.com/gallery.jpg", "is_main": False},
            ],
        )
        db_specs = pin_images_for_db_row({"pin_images": specs})
        self.assertEqual(sum(1 for s in db_specs if s["is_main"]), 1)
        self.assertTrue(db_specs[0]["is_main"])

    def test_count_pending_transform(self) -> None:
        documents = [
            {"contentid": "1", "pin_content": "a"},
            {"contentid": "2", "pin_content": "b"},
        ]
        handoff = {
            "1": {
                "contentid": "1",
                "pin_content_raw": "a",
                "pin_content": "done",
                "pin_title": "t",
            },
        }
        self.assertEqual(count_pending_transform(documents, handoff), 1)
        pending = list_pending_transform_rows(documents, handoff)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["contentid"], "2")

    def test_current_year_festival_range(self) -> None:
        from datetime import date

        start, end = current_year_festival_range(ref=date(2026, 6, 1))
        self.assertEqual(start, "20260601")
        self.assertEqual(end, "20261231")

    def test_validate_area_code(self) -> None:
        self.assertEqual(validate_area_code("1"), "1")
        self.assertEqual(validate_area_code("31"), "31")
        with self.assertRaises(ValueError):
            validate_area_code("99")

    def test_validate_sigungu_requires_area(self) -> None:
        with self.assertRaises(ValueError):
            validate_sigungu_code("1", area_code=None)

    def test_row_matches_area_filter(self) -> None:
        row = {"area_code": "1", "sigungu_code": "3"}
        self.assertTrue(row_matches_area_filter(row, area_code=None, sigungu_code=None))
        self.assertTrue(row_matches_area_filter(row, area_code="1", sigungu_code=None))
        self.assertTrue(row_matches_area_filter(row, area_code="1", sigungu_code="3"))
        self.assertFalse(row_matches_area_filter(row, area_code="6", sigungu_code=None))
        self.assertFalse(row_matches_area_filter(row, area_code="1", sigungu_code="9"))

    def test_infer_area_code_from_addr(self) -> None:
        self.assertEqual(infer_area_code_from_addr("서울특별시 강동구"), "1")
        self.assertEqual(infer_area_code_from_addr("경기도 수원시"), "31")
        self.assertIsNone(infer_area_code_from_addr(""))

    def test_resolve_row_area_code_prefers_areacode_over_empty_addr(self) -> None:
        self.assertEqual(
            resolve_row_area_code({"areacode": "1", "addr1": ""}),
            "1",
        )
        self.assertEqual(
            resolve_row_area_code({"areacode": "31", "addr1": "알 수 없는 주소"}),
            "31",
        )

    def test_extract_pet_friendly_skips_none_detail_values(self) -> None:
        payload = {
            "response": {
                "body": {
                    "items": {
                        "item": {
                            "petcomment": None,
                            "petdetail": "소형견 가능",
                        },
                    },
                },
            },
        }
        self.assertEqual(
            extract_pet_friendly(pet_tour_payload=payload, intro_payload=None),
            "소형견 가능",
        )

    def test_parse_event_datetime(self) -> None:
        self.assertEqual(_parse_event_datetime("20260701"), datetime(2026, 7, 1))


class FestivalImportBatchTest(unittest.IsolatedAsyncioTestCase):
    _MISSING_DOCS = Path("/tmp/issueissyu-missing-festival-documents.jsonl")

    async def test_transform_documents_batch_admin_batch_size_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "5 또는 25"):
            await transform_documents_batch(
                batch_size=10,
                input_path=self._MISSING_DOCS,
            )

    async def test_transform_documents_batch_allows_bulk_batch_size(self) -> None:
        with self.assertRaises(FileNotFoundError):
            await transform_documents_batch(
                batch_size=10,
                page_size=10,
                input_path=self._MISSING_DOCS,
                enforce_admin_batch_limits=False,
            )

    async def test_import_batch_skips_existing_when_allow_update_false(self) -> None:
        service = FestivalEventIngestService(
            pin_repo=MagicMock(),
            event_pin_repo=MagicMock(),
            pin_location_repo=MagicMock(),
            pin_image_repo=MagicMock(),
            location_resolve_client=MagicMock(),
        )
        service._event_pin_repo.list_festival_api_ids = AsyncMock(return_value={100})
        service._event_pin_repo.get_by_festival_api_id = AsyncMock()
        service._pin_repo.commit = AsyncMock()

        handoff_path = __import__(
            "app.services.festival_pin_transform",
            fromlist=["FESTIVAL_HANDOFF_PATH"],
        ).FESTIVAL_HANDOFF_PATH
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.write_text(
            '{"contentid":"100","festival_api_id":100,"pin_title":"A","pin_content":"B",'
            '"pin_content_raw":"R","event_start_time":"20260701","event_end_time":"20260702",'
            '"latitude":"37.5","longitude":"127.0","image_urls":[],"addr":"서울"}\n',
            encoding="utf-8",
        )

        result = await service.import_batch(admin_uid="admin-uid", batch_size=5, allow_update=False)
        self.assertEqual(result.inserted_count, 0)
        self.assertEqual(result.skipped_duplicate_count, 1)
        service._pin_repo.commit.assert_awaited_once()

    async def test_import_batch_uses_savepoint_per_row(self) -> None:
        mock_session = MagicMock()
        nested_ctx = MagicMock()
        nested_ctx.__aenter__ = AsyncMock(return_value=None)
        nested_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin_nested = MagicMock(return_value=nested_ctx)

        pin_repo = MagicMock()
        pin_repo.session = mock_session
        pin_repo.commit = AsyncMock()

        service = FestivalEventIngestService(
            pin_repo=pin_repo,
            event_pin_repo=MagicMock(),
            pin_location_repo=MagicMock(),
            pin_image_repo=MagicMock(),
            location_resolve_client=MagicMock(),
        )
        service._event_pin_repo.list_festival_api_ids = AsyncMock(return_value=set())
        service._event_pin_repo.get_by_festival_api_id = AsyncMock(return_value=None)
        service._insert_festival_pin = AsyncMock(side_effect=ValueError("위치 resolve 실패"))

        handoff_path = __import__(
            "app.services.festival_pin_transform",
            fromlist=["FESTIVAL_HANDOFF_PATH"],
        ).FESTIVAL_HANDOFF_PATH
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.write_text(
            '{"contentid":"101","festival_api_id":101,"pin_title":"A","pin_content":"B",'
            '"pin_content_raw":"R","event_start_time":"20260701","event_end_time":"20260702",'
            '"latitude":"37.5","longitude":"127.0","image_urls":[],"addr":"서울"}\n',
            encoding="utf-8",
        )

        result = await service.import_batch(admin_uid="admin-uid", batch_size=5, allow_update=False)
        self.assertEqual(result.error_count, 1)
        mock_session.begin_nested.assert_called_once()
        pin_repo.commit.assert_awaited_once()

    async def test_import_all_delegates_to_import_handoff_rows(self) -> None:
        service = FestivalEventIngestService(
            pin_repo=MagicMock(),
            event_pin_repo=MagicMock(),
            pin_location_repo=MagicMock(),
            pin_image_repo=MagicMock(),
            location_resolve_client=MagicMock(),
        )
        expected = FestivalImportBatchResult(
            import_all=True,
            inserted_count=10,
            updated_count=0,
            skipped_duplicate_count=0,
            pending_import_count=0,
            error_count=0,
        )
        service._import_handoff_rows = AsyncMock(return_value=expected)

        result = await service.import_all(admin_uid="admin-uid", allow_update=False)
        service._import_handoff_rows.assert_awaited_once_with(
            admin_uid="admin-uid",
            batch_size=None,
            allow_update=False,
            import_all=True,
            area_code=None,
            sigungu_code=None,
        )
        self.assertEqual(result.inserted_count, 10)
        self.assertTrue(result.import_all)


class FestivalResetCacheTest(unittest.TestCase):
    def test_reset_festival_dedup_cache(self) -> None:
        from app.services.festival_pin_transform import (
            FESTIVAL_DOCUMENTS_PATH,
            reset_festival_dedup_cache,
        )

        FESTIVAL_DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        FESTIVAL_DOCUMENTS_PATH.write_text('{"contentid":"1"}\n', encoding="utf-8")
        deleted = reset_festival_dedup_cache()
        self.assertIn(str(FESTIVAL_DOCUMENTS_PATH), deleted)
        self.assertFalse(FESTIVAL_DOCUMENTS_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
