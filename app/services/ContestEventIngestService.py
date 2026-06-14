from __future__ import annotations

import json
import logging
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from anyio import to_thread
from app.core.config import settings
from app.models.CardnewsImageS3 import CardnewsImageS3
from app.models.Community import Community
from app.models.EventPin import EventPin
from app.models.Pin import Pin
from app.models.PinImage import PinImage
from app.models.enum.PinType import PinType
from app.models.enum.ToneType import ToneType
from app.repositories.CardnewsImageS3Repo import CardnewsImageS3Repo
from app.repositories.CommunityRepo import CommunityRepo
from app.repositories.EventPinRepo import EventPinRepo
from app.repositories.PinImageRepo import PinImageRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.ContestAdminDTO import (
    ContestBatchAction,
    ContestBatchItemResult,
    ContestImportBatchResult,
    ContestPipelineStatusResult,
)
from app.services.contest_pipeline_cleanup import cleanup_after_contest_import
from app.services.contest_pin_transform import (
    CONTEST_DOCUMENTS_PATH,
    CONTEST_HANDOFF_PATH,
    CONTEST_SYNC_META_PATH,
    count_pending_transform,
    load_jsonl_rows,
    load_rows_by_content_id,
    parse_contest_api_id,
)
from app.utils.contest_images import CONTEST_IMAGE_S3_KEY, pin_images_for_db_row
from rag.scripts.fetch_linkareer_contests import is_contest_row_expired

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_IMPORT_REPORT_PATH = CONTEST_HANDOFF_PATH.with_name("contest_import_batch_report.json")
_COMMUNITY_TYPE_CONTEST = "CONTEST"


def _parse_event_datetime(value: Any) -> datetime:
    if value is None:
        raise ValueError("event datetime 없음")
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    if not text:
        raise ValueError("event datetime 비어 있음")
    if len(text) == 8 and text.isdigit():
        year, month, day = int(text[:4]), int(text[4:6]), int(text[6:8])
        return datetime(year, month, day)
    raise ValueError(f"event datetime 파싱 실패: {value!r}")


def _event_window_from_row(row: dict[str, Any]) -> tuple[datetime, datetime]:
    start_raw = row.get("event_start_time")
    end_raw = row.get("event_end_time") or start_raw
    if not start_raw:
        today = datetime.now(_KST).date()
        start_raw = today.strftime("%Y%m%d")
        end_raw = end_raw or start_raw
    start_dt = _parse_event_datetime(start_raw)
    end_dt = _parse_event_datetime(end_raw)
    if end_dt < start_dt:
        end_dt = start_dt
    start_at = datetime.combine(start_dt.date(), time.min)
    end_at = datetime.combine(end_dt.date(), time.max.replace(microsecond=0))
    return start_at, end_at


class ContestEventIngestService:
    def __init__(
        self,
        *,
        pin_repo: PinRepo,
        event_pin_repo: EventPinRepo,
        community_repo: CommunityRepo,
        cardnews_image_s3_repo: CardnewsImageS3Repo,
        pin_image_repo: PinImageRepo,
        user_repo: UserRepo,
    ) -> None:
        self._pin_repo = pin_repo
        self._event_pin_repo = event_pin_repo
        self._community_repo = community_repo
        self._cardnews_image_s3_repo = cardnews_image_s3_repo
        self._pin_image_repo = pin_image_repo
        self._user_repo = user_repo

    async def commit(self) -> None:
        await self._pin_repo.commit()

    async def rollback(self) -> None:
        await self._pin_repo.rollback()

    async def get_imported_contest_api_ids(self) -> set[int]:
        return await self._event_pin_repo.list_contest_api_ids()

    async def resolve_admin_uid(self) -> str:
        user_name = settings.contest_admin_user_name.strip()
        user = await self._user_repo.get_by_user_name(user_name)
        if user is None:
            raise RuntimeError(
                f"공모전 핀 등록용 사용자를 찾을 수 없습니다 (user_name={user_name!r}).",
            )
        return str(user.uid)

    async def import_handoff_batch(
        self,
        *,
        admin_uid: str | None = None,
        import_all: bool = True,
        limit: int | None = None,
    ) -> ContestImportBatchResult:
        handoff_rows = await to_thread.run_sync(load_jsonl_rows, CONTEST_HANDOFF_PATH)
        db_ids = await self.get_imported_contest_api_ids()
        if not handoff_rows:
            documents = await to_thread.run_sync(load_jsonl_rows, CONTEST_DOCUMENTS_PATH)
            pending_transform = count_pending_transform(documents, {}, db_contest_api_ids=db_ids)
            if pending_transform > 0:
                raise FileNotFoundError(
                    f"핸드오프 JSONL 없음: {CONTEST_HANDOFF_PATH}. "
                    f"transform을 먼저 실행하세요. (미가공 {pending_transform}건)",
                )
            effective_batch = None if import_all else limit
            return ContestImportBatchResult(
                inserted_count=0,
                skipped_duplicate_count=0,
                skipped_expired_count=0,
                pending_import_count=0,
                error_count=0,
                requested_batch_size=effective_batch,
                hint=(
                    f"DB에 contest 핀 {len(db_ids)}건이 있어 적재 완료 상태입니다. "
                    "handoff JSONL이 비어 있는 것은 import 후 캐시 정리로 정상입니다."
                ),
            )

        uid = admin_uid or await self.resolve_admin_uid()
        inserted_count = 0
        skipped_duplicate_count = 0
        skipped_expired_count = 0
        errors: list[dict[str, Any]] = []
        items: list[ContestBatchItemResult] = []
        pin_ids: list[int] = []
        prune_contest_api_ids: set[int] = set()

        pending_rows: list[dict[str, Any]] = []
        for row in handoff_rows:
            contest_api_id = parse_contest_api_id(row)
            if contest_api_id is None:
                continue
            if is_contest_row_expired(row):
                skipped_expired_count += 1
                prune_contest_api_ids.add(contest_api_id)
                items.append(
                    ContestBatchItemResult(
                        contest_api_id=contest_api_id,
                        pin_title=str(row.get("title") or row.get("pin_title") or ""),
                        action=ContestBatchAction.SKIPPED,
                        message="종료일 경과",
                    ),
                )
                continue
            if contest_api_id in db_ids:
                skipped_duplicate_count += 1
                prune_contest_api_ids.add(contest_api_id)
                items.append(
                    ContestBatchItemResult(
                        contest_api_id=contest_api_id,
                        pin_title=str(row.get("title") or row.get("pin_title") or ""),
                        action=ContestBatchAction.SKIPPED,
                        message="DB에 이미 존재",
                    ),
                )
            else:
                pending_rows.append(row)

        target_rows = pending_rows if import_all else pending_rows[: (limit or len(pending_rows))]
        if limit is not None and import_all:
            target_rows = pending_rows[:limit]

        for row in target_rows:
            contest_api_id = parse_contest_api_id(row)
            if contest_api_id is None:
                errors.append({"row": row, "error": "contest_api_id 없음"})
                continue
            if is_contest_row_expired(row):
                skipped_expired_count += 1
                prune_contest_api_ids.add(contest_api_id)
                items.append(
                    ContestBatchItemResult(
                        contest_api_id=contest_api_id,
                        pin_title=str(row.get("title") or row.get("pin_title") or ""),
                        action=ContestBatchAction.SKIPPED,
                        message="종료일 경과",
                    ),
                )
                continue
            if contest_api_id in db_ids:
                skipped_duplicate_count += 1
                prune_contest_api_ids.add(contest_api_id)
                continue
            try:
                async with self._pin_repo.session.begin_nested():
                    pin_id = await self._insert_contest_pin(
                        admin_uid=uid,
                        row=row,
                        contest_api_id=contest_api_id,
                    )
                inserted_count += 1
                db_ids.add(contest_api_id)
                prune_contest_api_ids.add(contest_api_id)
                pin_ids.append(pin_id)
                items.append(
                    ContestBatchItemResult(
                        contest_api_id=contest_api_id,
                        pin_title=str(row.get("title") or row.get("pin_title") or ""),
                        action=ContestBatchAction.CREATED,
                    ),
                )
            except Exception as exc:
                logger.exception("contest import failed contest_api_id=%s", contest_api_id)
                errors.append(
                    {
                        "contest_api_id": contest_api_id,
                        "pin_title": row.get("title") or row.get("pin_title"),
                        "error": str(exc),
                    },
                )
                items.append(
                    ContestBatchItemResult(
                        contest_api_id=contest_api_id,
                        pin_title=str(row.get("title") or row.get("pin_title") or ""),
                        action=ContestBatchAction.ERROR,
                        message=str(exc),
                    ),
                )

        await self._pin_repo.commit()

        if settings.contest_prune_pipeline_after_import and prune_contest_api_ids:
            await to_thread.run_sync(cleanup_after_contest_import, prune_contest_api_ids)

        pending_import = 0
        for row in handoff_rows:
            contest_api_id = parse_contest_api_id(row)
            if contest_api_id is not None and contest_api_id not in db_ids and not is_contest_row_expired(row):
                pending_import += 1

        report = {
            "inserted_count": inserted_count,
            "skipped_duplicate_count": skipped_duplicate_count,
            "skipped_expired_count": skipped_expired_count,
            "errors": errors,
        }
        _IMPORT_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        effective_batch = None if import_all else limit
        return ContestImportBatchResult(
            inserted_count=inserted_count,
            skipped_duplicate_count=skipped_duplicate_count,
            skipped_expired_count=skipped_expired_count,
            pending_import_count=pending_import,
            error_count=len(errors),
            errors=errors,
            items=items,
            pin_ids=pin_ids,
            requested_batch_size=effective_batch,
        )

    async def _insert_contest_pin(
        self,
        *,
        admin_uid: str,
        row: dict[str, Any],
        contest_api_id: int,
    ) -> int:
        title = str(row.get("title") or row.get("pin_title") or "").strip()[:100]
        content = str(row.get("pin_content") or "").strip()
        if not title or not content:
            raise ValueError("title 또는 pin_content가 비어 있음")

        start_at, end_at = _event_window_from_row(row)

        pin = Pin(
            uid=admin_uid,
            pin_type=PinType.CONTEST,
            pin_title=title,
            pin_content=content,
            tone_type=ToneType.NONE,
            like_count=0,
            view_count=0,
        )
        await self._pin_repo.save(pin, flush_immediately=True)

        event_pin = EventPin(
            pin_id=pin.pin_id,
            festival_api_id=None,
            policy_api_id=None,
            contest_api_id=contest_api_id,
            event_start_time=start_at,
            event_end_time=end_at,
            discount=None,
        )
        await self._event_pin_repo.save(event_pin, flush_immediately=True)

        community = Community(
            pin_id=pin.pin_id,
            community_type=_COMMUNITY_TYPE_CONTEST,
            popularity=0.0,
        )
        await self._community_repo.save(community, flush_immediately=True)

        for spec in pin_images_for_db_row(row):
            url = str(spec.get("pin_image_url") or "").strip()
            if not url:
                continue
            pin_image = PinImage(
                pin_id=pin.pin_id,
                pin_s3_key=CONTEST_IMAGE_S3_KEY,
                pin_s3_url=url,
                is_main=bool(spec.get("is_main")),
            )
            await self._pin_image_repo.save(pin_image, flush_immediately=True)

        cardnews_images = row.get("cardnews_images") or []
        for image in cardnews_images:
            if not isinstance(image, dict):
                continue
            key = str(image.get("key") or "").strip()
            url = str(image.get("url") or "").strip()
            if not key or not url:
                continue
            entity = CardnewsImageS3(
                community_id=community.community_id,
                cardnews_image_s3_key=key,
                cardnews_image_s3_url=url,
            )
            await self._cardnews_image_s3_repo.save(entity, flush_immediately=True)

        return int(pin.pin_id)

    async def get_pipeline_status(self) -> ContestPipelineStatusResult:
        meta = self._load_sync_meta()
        documents = load_jsonl_rows(CONTEST_DOCUMENTS_PATH)
        handoff_by_id = load_rows_by_content_id(CONTEST_HANDOFF_PATH)
        db_ids = await self.get_imported_contest_api_ids()

        pending_transform = count_pending_transform(documents, handoff_by_id, db_contest_api_ids=db_ids)
        pending_import = 0
        for row in handoff_by_id.values():
            contest_api_id = parse_contest_api_id(row)
            if contest_api_id is not None and contest_api_id not in db_ids:
                pending_import += 1

        is_caught_up = pending_transform == 0 and pending_import == 0
        hint: str | None = None
        if is_caught_up and len(db_ids) > 0:
            hint = (
                f"DB에 contest 핀 {len(db_ids)}건 반영 완료. "
                "handoff_count=0은 import 후 JSONL 캐시 정리로 정상입니다."
            )
        elif pending_transform > 0:
            hint = f"미가공 {pending_transform}건 — transform-batch 또는 sync를 실행하세요."
        elif pending_import > 0:
            hint = f"미적재 {pending_import}건 — import-batch 또는 sync를 실행하세요."

        return ContestPipelineStatusResult(
            last_sync_at=meta.get("last_sync_at"),
            documents_count=len(documents),
            handoff_count=len(handoff_by_id),
            db_contest_count=len(db_ids),
            pending_transform_count=pending_transform,
            pending_import_count=pending_import,
            is_caught_up=is_caught_up,
            hint=hint,
        )

    @staticmethod
    def _load_sync_meta() -> dict[str, Any]:
        if not CONTEST_SYNC_META_PATH.is_file():
            return {}
        try:
            return json.loads(CONTEST_SYNC_META_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def write_sync_meta() -> None:
        meta = {
            "last_sync_at": datetime.now(_KST).isoformat(timespec="seconds"),
        }
        CONTEST_SYNC_META_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTEST_SYNC_META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
