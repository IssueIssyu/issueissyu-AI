from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.VisitKoreaClient import VisitKoreaClient
from app.core.config import settings
from app.models.EventPin import EventPin
from app.models.Pin import Pin
from app.models.PinImage import PinImage
from app.models.PinLocation import PinLocation
from app.models.enum.PinType import PinType
from app.models.enum.ToneType import ToneType
from app.repositories.EventPinRepo import EventPinRepo
from app.repositories.PinImageRepo import PinImageRepo
from app.repositories.PinLocationRepo import PinLocationRepo
from app.repositories.PinRepo import PinRepo
from app.schemas.FestivalAdminDTO import (
    FestivalBatchAction,
    FestivalBatchItemResult,
    FestivalFetchResult,
    FestivalImportBatchResult,
    FestivalPipelineResetResult,
    FestivalPipelineStatusResult,
    FestivalTransformBatchResult,
)
from app.schemas.FestivalPinDTO import FestivalPinDTO, FestivalPinHandoffResult
from app.services.festival_pin_transform import (
    FESTIVAL_DOCUMENTS_PATH,
    FESTIVAL_HANDOFF_PATH,
    FESTIVAL_IMAGE_S3_KEY,
    FESTIVAL_PIPELINE_META_PATH,
    count_pending_transform,
    load_jsonl_rows,
    load_rows_by_content_id,
    merge_documents,
    parse_festival_api_id,
    row_content_id,
    transform_documents_batch,
    write_handoff_map,
    reset_festival_dedup_cache,
)
from app.services.internal.geo.LocationResolveClient import LocationResolveClient
from app.services.internal.geo.location_resolve_fields import resolve_pin_location_fields
from app.utils.festival_date_filter import current_year_festival_range, festival_overlaps_range
from app.utils.visitkorea_area import area_display_name, resolve_row_area_code, row_matches_area_filter
from rag.scripts.chunk_module import write_jsonl
from rag.scripts.fetch_visitkorea import (
    FESTIVAL_CONTENT_TYPE_ID,
    _fetch_festival_item_details,
    build_document_row,
    collect_pin_image_specs,
    pin_images_for_db_row,
    extract_pet_friendly,
    extract_stay_available,
    tourapi_body_items,
    tourapi_result_ok,
    tourapi_total_count as get_tourapi_total_count,
)

logger = logging.getLogger(__name__)

_IMPORT_REPORT_PATH = FESTIVAL_HANDOFF_PATH.with_name("festival_import_batch_report.json")


def _discard_session_state_after_nested_failure(session: AsyncSession) -> None:
    """SAVEPOINT 롤백 후 session.new/dirty에 남은 객체가 다음 flush·commit에 재시도되지 않도록 정리."""
    for obj in list(session.new):
        session.expunge(obj)
    for obj in list(session.dirty):
        session.expire(obj)


class FestivalEventIngestService:
    def __init__(
        self,
        *,
        pin_repo: PinRepo,
        event_pin_repo: EventPinRepo,
        pin_location_repo: PinLocationRepo,
        pin_image_repo: PinImageRepo,
        location_resolve_client: LocationResolveClient,
    ) -> None:
        self._pin_repo = pin_repo
        self._event_pin_repo = event_pin_repo
        self._pin_location_repo = pin_location_repo
        self._pin_image_repo = pin_image_repo
        self._location_resolve_client = location_resolve_client

    async def commit(self) -> None:
        await self._pin_repo.commit()

    async def rollback(self) -> None:
        await self._pin_repo.rollback()

    async def fetch_and_save(
        self,
        *,
        start_date: str,
        end_date: str,
        limit: int | None = None,
        area_code: str | None = None,
        sigungu_code: str | None = None,
    ) -> FestivalFetchResult:
        existing_by_id = load_rows_by_content_id(FESTIVAL_DOCUMENTS_PATH)
        added_rows: list[dict[str, Any]] = []
        skipped_duplicate_count = 0
        skipped_area_count = 0
        tourapi_total_count_val = 0

        FESTIVAL_DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not FESTIVAL_DOCUMENTS_PATH.is_file():
            write_jsonl(FESTIVAL_DOCUMENTS_PATH, list(existing_by_id.values()))

        async with VisitKoreaClient.from_settings() as client:
            page_no = 1
            while limit is None or len(added_rows) < limit:
                list_payload = await client.search_festival(
                    event_start_date=start_date,
                    event_end_date=end_date,
                    page_no=page_no,
                    num_of_rows=100,
                )
                ok, msg = tourapi_result_ok(list_payload)
                if not ok:
                    raise RuntimeError(f"searchFestival2 실패: {msg}")
                if page_no == 1:
                    tourapi_total_count_val = get_tourapi_total_count(list_payload)

                items = tourapi_body_items(list_payload)
                if not items:
                    break

                for list_item in items:
                    if limit is not None and len(added_rows) >= limit:
                        break
                    content_id = str(list_item.get("contentid") or "").strip()
                    if not content_id:
                        continue
                    if content_id in existing_by_id:
                        skipped_duplicate_count += 1
                        continue

                    if area_code is not None:
                        item_area = resolve_row_area_code(list_item)
                        if item_area != area_code:
                            skipped_area_count += 1
                            continue

                    content_type_id = str(
                        list_item.get("contenttypeid") or FESTIVAL_CONTENT_TYPE_ID,
                    ).strip()
                    details = await _fetch_festival_item_details(
                        client,
                        content_id=content_id,
                        content_type_id=content_type_id,
                        fetch_images=True,
                    )
                    pin_images = collect_pin_image_specs(
                        list_item,
                        details.common_item,
                        details.image_payload,
                    )
                    pet_friendly = extract_pet_friendly(
                        pet_tour_payload=details.pet_tour_payload,
                        intro_payload=details.intro_payload,
                    )
                    stay_available = extract_stay_available(intro_payload=details.intro_payload)
                    row = build_document_row(
                        list_item=list_item,
                        common_item=details.common_item,
                        intro_text=details.intro_text,
                        pin_images=pin_images,
                        pet_friendly=pet_friendly,
                        stay_available=stay_available,
                    )
                    if row is None:
                        continue
                    if not row_matches_area_filter(
                        row,
                        area_code=area_code,
                        sigungu_code=sigungu_code,
                    ):
                        skipped_area_count += 1
                        continue
                    added_rows.append(row)
                    existing_by_id[content_id] = row

                self._persist_documents(existing_by_id)

                if tourapi_total_count_val and page_no * 100 >= tourapi_total_count_val:
                    break
                if len(items) < 100:
                    break
                page_no += 1

        merged = self._persist_documents(existing_by_id)
        self._save_pipeline_meta(
            start_date=start_date,
            end_date=end_date,
            tourapi_total_count=tourapi_total_count_val,
            area_code=area_code,
            sigungu_code=sigungu_code,
        )

        handoff_by_id = load_rows_by_content_id(FESTIVAL_HANDOFF_PATH)
        pending_transform = count_pending_transform(
            merged,
            handoff_by_id,
            area_code=area_code,
            sigungu_code=sigungu_code,
        )

        return FestivalFetchResult(
            query_start_date=start_date,
            query_end_date=end_date,
            requested_limit=limit,
            area_code=area_code,
            sigungu_code=sigungu_code,
            area_name=area_display_name(area_code),
            tourapi_total_count=tourapi_total_count_val,
            added_count=len(added_rows),
            skipped_duplicate_count=skipped_duplicate_count,
            skipped_area_count=skipped_area_count,
            total_in_documents=len(merged),
            pending_transform_count=pending_transform,
            saved_documents_path=str(FESTIVAL_DOCUMENTS_PATH),
            pins=added_rows,
        )

    async def fetch_year_and_save(
        self,
        *,
        area_code: str | None = None,
        sigungu_code: str | None = None,
    ) -> FestivalFetchResult:
        start_date, end_date = current_year_festival_range()
        return await self.fetch_and_save(
            start_date=start_date,
            end_date=end_date,
            limit=None,
            area_code=area_code,
            sigungu_code=sigungu_code,
        )

    async def transform_batch(
        self,
        *,
        batch_size: int | None = None,
        page: int = 1,
        page_size: int = 25,
        area_code: str | None = None,
        sigungu_code: str | None = None,
        model: str | None = None,
    ) -> FestivalTransformBatchResult:
        handoff_by_id, processed_rows, errors, skipped, page_meta = await transform_documents_batch(
            batch_size=batch_size,
            page=page,
            page_size=page_size,
            area_code=area_code,
            sigungu_code=sigungu_code,
            model=model,
        )
        documents = load_jsonl_rows(FESTIVAL_DOCUMENTS_PATH)
        pending_transform = count_pending_transform(
            documents,
            handoff_by_id,
            area_code=area_code,
            sigungu_code=sigungu_code,
        )

        items: list[FestivalBatchItemResult] = []
        for row in processed_rows:
            items.append(
                FestivalBatchItemResult(
                    festival_api_id=parse_festival_api_id(row),
                    pin_title=str(row.get("pin_title") or ""),
                    action=FestivalBatchAction.CREATED,
                ),
            )
        for _ in range(skipped):
            items.append(
                FestivalBatchItemResult(
                    action=FestivalBatchAction.SKIPPED,
                    message="이미 가공된 동일 원문",
                ),
            )

        pins = [FestivalPinDTO.model_validate(row) for row in processed_rows]
        return FestivalTransformBatchResult(
            page=page_meta["page"],
            page_size=page_meta["page_size"],
            total_pages=page_meta["total_pages"],
            total_pending_before_page=page_meta["total_pending_before_page"],
            requested_batch_size=page_meta["requested_batch_size"],
            area_code=area_code,
            sigungu_code=sigungu_code,
            area_name=area_display_name(area_code),
            processed_count=len(processed_rows),
            skipped_duplicate_count=skipped,
            pending_transform_count=pending_transform,
            error_count=len(errors),
            errors=errors,
            items=items,
            pins=pins,
            output_path=str(FESTIVAL_HANDOFF_PATH),
        )

    async def import_batch(
        self,
        *,
        admin_uid: str,
        batch_size: int,
        allow_update: bool = False,
        area_code: str | None = None,
        sigungu_code: str | None = None,
    ) -> FestivalImportBatchResult:
        return await self._import_handoff_rows(
            admin_uid=admin_uid,
            batch_size=batch_size,
            allow_update=allow_update,
            import_all=False,
            area_code=area_code,
            sigungu_code=sigungu_code,
        )

    async def import_all(
        self,
        *,
        admin_uid: str,
        allow_update: bool = False,
        area_code: str | None = None,
        sigungu_code: str | None = None,
    ) -> FestivalImportBatchResult:
        return await self._import_handoff_rows(
            admin_uid=admin_uid,
            batch_size=None,
            allow_update=allow_update,
            import_all=True,
            area_code=area_code,
            sigungu_code=sigungu_code,
        )

    async def _import_handoff_rows(
        self,
        *,
        admin_uid: str,
        batch_size: int | None,
        allow_update: bool,
        import_all: bool,
        area_code: str | None = None,
        sigungu_code: str | None = None,
    ) -> FestivalImportBatchResult:
        handoff_rows = load_jsonl_rows(FESTIVAL_HANDOFF_PATH)
        if not handoff_rows:
            raise FileNotFoundError(
                f"핸드오프 JSONL 없음: {FESTIVAL_HANDOFF_PATH}. transform-batch를 먼저 실행하세요.",
            )

        db_ids = await self._event_pin_repo.list_festival_api_ids()
        inserted_count = 0
        updated_count = 0
        skipped_duplicate_count = 0
        errors: list[dict[str, Any]] = []
        items: list[FestivalBatchItemResult] = []
        pin_ids: list[int] = []

        pending_rows: list[dict[str, Any]] = []
        for row in handoff_rows:
            if not row_matches_area_filter(row, area_code=area_code, sigungu_code=sigungu_code):
                continue
            festival_api_id = parse_festival_api_id(row)
            if festival_api_id is None:
                continue
            if festival_api_id in db_ids:
                if allow_update:
                    pending_rows.append(row)
                else:
                    skipped_duplicate_count += 1
                    items.append(
                        FestivalBatchItemResult(
                            festival_api_id=festival_api_id,
                            pin_title=str(row.get("pin_title") or ""),
                            action=FestivalBatchAction.SKIPPED,
                            message="DB에 이미 존재",
                        ),
                    )
            else:
                pending_rows.append(row)

        target_rows = pending_rows if import_all else pending_rows[:batch_size]
        for row in target_rows:
            festival_api_id = parse_festival_api_id(row)
            if festival_api_id is None:
                errors.append({"row": row, "error": "festival_api_id 없음"})
                continue
            existing = await self._event_pin_repo.get_by_festival_api_id(festival_api_id)
            try:
                async with self._pin_repo.session.begin_nested():
                    if existing is None:
                        pin_id = await self._insert_festival_pin(
                            admin_uid=admin_uid,
                            row=row,
                            festival_api_id=festival_api_id,
                        )
                        inserted_count += 1
                        db_ids.add(festival_api_id)
                        pin_ids.append(pin_id)
                        items.append(
                            FestivalBatchItemResult(
                                festival_api_id=festival_api_id,
                                pin_title=str(row.get("pin_title") or ""),
                                action=FestivalBatchAction.CREATED,
                            ),
                        )
                    elif allow_update:
                        pin_id = await self._update_festival_pin(existing=existing, row=row)
                        updated_count += 1
                        pin_ids.append(pin_id)
                        items.append(
                            FestivalBatchItemResult(
                                festival_api_id=festival_api_id,
                                pin_title=str(row.get("pin_title") or ""),
                                action=FestivalBatchAction.UPDATED,
                            ),
                        )
            except Exception as exc:
                _discard_session_state_after_nested_failure(self._pin_repo.session)
                logger.exception("festival import failed festival_api_id=%s", festival_api_id)
                errors.append(
                    {
                        "festival_api_id": festival_api_id,
                        "pin_title": row.get("pin_title"),
                        "error": str(exc),
                    },
                )
                items.append(
                    FestivalBatchItemResult(
                        festival_api_id=festival_api_id,
                        pin_title=str(row.get("pin_title") or ""),
                        action=FestivalBatchAction.ERROR,
                        message=str(exc),
                    ),
                )

        await self._pin_repo.commit()

        pending_import = 0
        for row in handoff_rows:
            if not row_matches_area_filter(row, area_code=area_code, sigungu_code=sigungu_code):
                continue
            festival_api_id = parse_festival_api_id(row)
            if festival_api_id is None:
                continue
            if festival_api_id not in db_ids:
                pending_import += 1

        report = {
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "skipped_duplicate_count": skipped_duplicate_count,
            "errors": errors,
        }
        _IMPORT_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        return FestivalImportBatchResult(
            requested_batch_size=batch_size,
            import_all=import_all,
            area_code=area_code,
            sigungu_code=sigungu_code,
            area_name=area_display_name(area_code),
            inserted_count=inserted_count,
            updated_count=updated_count,
            skipped_duplicate_count=skipped_duplicate_count,
            pending_import_count=pending_import,
            error_count=len(errors),
            errors=errors,
            items=items,
            pin_ids=pin_ids,
        )

    def reset_dedup_cache(self) -> FestivalPipelineResetResult:
        deleted = reset_festival_dedup_cache()
        return FestivalPipelineResetResult(deleted_files=deleted)

    async def get_pipeline_status(self) -> FestivalPipelineStatusResult:
        meta = self._load_pipeline_meta()
        documents = load_jsonl_rows(FESTIVAL_DOCUMENTS_PATH)
        handoff_by_id = load_rows_by_content_id(FESTIVAL_HANDOFF_PATH)
        db_ids = await self._event_pin_repo.list_festival_api_ids()

        pending_transform = count_pending_transform(documents, handoff_by_id)
        pending_import = 0
        for row in handoff_by_id.values():
            festival_api_id = parse_festival_api_id(row)
            if festival_api_id is not None and festival_api_id not in db_ids:
                pending_import += 1

        return FestivalPipelineStatusResult(
            tourapi_total_count=meta.get("tourapi_total_count"),
            query_start_date=meta.get("query_start_date"),
            query_end_date=meta.get("query_end_date"),
            area_code=meta.get("area_code"),
            sigungu_code=meta.get("sigungu_code"),
            area_name=meta.get("area_name") or area_display_name(meta.get("area_code")),
            documents_count=len(documents),
            handoff_count=len(handoff_by_id),
            db_festival_count=len(db_ids),
            pending_transform_count=pending_transform,
            pending_import_count=pending_import,
        )

    def load_handoff_preview(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> FestivalPinHandoffResult:
        path = FESTIVAL_HANDOFF_PATH
        if not path.is_file():
            raise FileNotFoundError(
                f"핸드오프 JSONL 없음: {path}. transform-batch를 먼저 실행하세요.",
            )

        effective_limit = 500 if limit is None else min(limit, 500)
        use_date_filter = start_date is not None and end_date is not None
        matched: list[FestivalPinDTO] = []
        total_in_file = 0

        for row in load_jsonl_rows(path):
            total_in_file += 1
            item = FestivalPinDTO.model_validate(row)
            if use_date_filter and not festival_overlaps_range(
                event_start=item.event_start_time,
                event_end=item.event_end_time,
                query_start=start_date,
                query_end=end_date,
            ):
                continue
            matched.append(item)

        pins = matched[:effective_limit]
        return FestivalPinHandoffResult(
            filter_start_date=start_date,
            filter_end_date=end_date,
            total_in_file=total_in_file,
            matched_count=len(matched),
            count=len(pins),
            pins=pins,
        )

    async def _insert_festival_pin(
        self,
        *,
        admin_uid: str,
        row: dict[str, Any],
        festival_api_id: int,
    ) -> int:
        location_fields = await self._resolve_location(row)
        if location_fields is None:
            raise ValueError("위치 resolve 실패")

        location_id, detail_address, pin_point = location_fields
        pin = Pin(
            uid=admin_uid,
            pin_type=PinType.FESTIVAL,
            pin_title=str(row.get("pin_title") or "")[:100],
            pin_content=str(row.get("pin_content") or ""),
            tone_type=ToneType.NONE,
            like_count=0,
            view_count=0,
        )
        await self._pin_repo.save(pin, flush_immediately=True)

        event_pin = EventPin(
            pin_id=pin.pin_id,
            festival_api_id=festival_api_id,
            event_start_time=_parse_event_datetime(row.get("event_start_time")),
            event_end_time=_parse_event_datetime(row.get("event_end_time")),
            discount=None,
        )
        await self._event_pin_repo.save(event_pin, flush_immediately=True)

        pin_location = PinLocation(
            pin_id=pin.pin_id,
            location_id=location_id,
            detail_address=detail_address,
            pin_point=pin_point,
        )
        await self._pin_location_repo.save(pin_location, flush_immediately=True)

        await self._replace_pin_images(pin_id=pin.pin_id, row=row)
        return int(pin.pin_id)

    async def _update_festival_pin(self, *, existing: EventPin, row: dict[str, Any]) -> int:
        pin = existing.pin
        if pin is None:
            raise ValueError("연결된 pin 없음")

        location_fields = await self._resolve_location(row)
        if location_fields is None:
            raise ValueError("위치 resolve 실패")
        location_id, detail_address, pin_point = location_fields

        pin.pin_title = str(row.get("pin_title") or pin.pin_title)[:100]
        pin.pin_content = str(row.get("pin_content") or pin.pin_content)
        await self._pin_repo.save(pin, flush_immediately=True)

        existing.event_start_time = _parse_event_datetime(row.get("event_start_time"))
        existing.event_end_time = _parse_event_datetime(row.get("event_end_time"))
        existing.discount = None
        await self._event_pin_repo.save(existing, flush_immediately=True)

        if pin.pin_location is None:
            pin_location = PinLocation(
                pin_id=pin.pin_id,
                location_id=location_id,
                detail_address=detail_address,
                pin_point=pin_point,
            )
            await self._pin_location_repo.save(pin_location, flush_immediately=True)
        else:
            pin.pin_location.location_id = location_id
            pin.pin_location.detail_address = detail_address
            pin.pin_location.pin_point = pin_point
            await self._pin_location_repo.save(pin.pin_location, flush_immediately=True)

        await self._pin_image_repo.delete_by_pin_id(pin.pin_id)
        await self._replace_pin_images(pin_id=pin.pin_id, row=row)
        return int(pin.pin_id)

    async def _replace_pin_images(self, *, pin_id: int, row: dict[str, Any]) -> None:
        for spec in pin_images_for_db_row(row):
            url = str(spec.get("pin_image_url") or "").strip()
            if not url:
                continue
            pin_image = PinImage(
                pin_id=pin_id,
                pin_s3_key=FESTIVAL_IMAGE_S3_KEY,
                pin_s3_url=url,
                is_main=bool(spec.get("is_main")),
            )
            await self._pin_image_repo.save(pin_image, flush_immediately=True)

    async def _resolve_location(self, row: dict[str, Any]):
        lat_raw = row.get("latitude")
        lng_raw = row.get("longitude")
        if lat_raw is None or lng_raw is None:
            return None
        try:
            latitude = float(str(lat_raw).strip())
            longitude = float(str(lng_raw).strip())
        except ValueError:
            return None
        return await resolve_pin_location_fields(
            self._location_resolve_client,
            latitude=latitude,
            longitude=longitude,
            addr_fallback=str(row.get("addr") or ""),
            prefer_addr_fallback=True,
            allow_nudge=True,
        )

    @staticmethod
    def _persist_documents(existing_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        merged = merge_documents({}, list(existing_by_id.values()))
        write_jsonl(FESTIVAL_DOCUMENTS_PATH, merged)
        return merged

    @staticmethod
    def _save_pipeline_meta(
        *,
        start_date: str,
        end_date: str,
        tourapi_total_count: int,
        area_code: str | None = None,
        sigungu_code: str | None = None,
    ) -> None:
        payload = {
            "query_start_date": start_date,
            "query_end_date": end_date,
            "tourapi_total_count": tourapi_total_count,
            "area_code": area_code,
            "sigungu_code": sigungu_code,
            "area_name": area_display_name(area_code),
        }
        FESTIVAL_PIPELINE_META_PATH.parent.mkdir(parents=True, exist_ok=True)
        FESTIVAL_PIPELINE_META_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _load_pipeline_meta() -> dict[str, Any]:
        if not FESTIVAL_PIPELINE_META_PATH.is_file():
            return {}
        try:
            payload = json.loads(FESTIVAL_PIPELINE_META_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}


def _parse_event_datetime(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("행사 날짜가 비어 있습니다.")
    return datetime.strptime(text, "%Y%m%d")
