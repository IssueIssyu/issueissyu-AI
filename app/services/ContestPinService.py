from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ContestAdminDTO import (
    ContestBatchAction,
    ContestBatchItemResult,
    ContestImportBatchResult,
    ContestSyncResult,
    ContestTransformBatchResult,
)
from app.schemas.ContestPinDTO import (
    ContestCrawlResult,
    ContestDocumentDTO,
    ContestDocumentsListResult,
    ContestPinHandoffResult,
    ContestPinTransformResult,
)
from app.services.ContestEventIngestService import ContestEventIngestService
from app.services.contest_pipeline_cleanup import prune_pipeline_imported
from app.services.contest_pin_transform import (
    CONTEST_HANDOFF_PATH,
    load_jsonl_rows,
    transform_documents_jsonl,
    load_handoff_from_jsonl,
)
from app.utils.S3Util import S3Util
from app.utils.festival_date_filter import festival_overlaps_range
from rag.scripts.fetch_linkareer_contests import (
    CONTEST_DOCUMENTS_PATH,
    normalize_contest_row,
    run_crawl,
)

_MAX_LIST_ITEMS = 500


def _ensure_playwright_ready() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "playwright 패키지가 없습니다. "
            "서버 venv에서: pip install playwright && python -m playwright install chromium"
        ) from exc


def _run_crawl_in_proactor_thread(
    *,
    max_pages: int,
    start_page: int,
    limit: int | None,
    delay: float,
    force: bool,
) -> dict[str, Any]:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            run_crawl(
                max_pages=max_pages,
                start_page=start_page,
                limit=limit,
                delay=delay,
                force=force,
            )
        )
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


class ContestPinService:
    @staticmethod
    def documents_path() -> Path:
        return CONTEST_DOCUMENTS_PATH

    @staticmethod
    def handoff_path() -> Path:
        return CONTEST_HANDOFF_PATH

    async def crawl_and_save(
        self,
        *,
        max_pages: int | None = None,
        start_page: int | None = None,
        limit: int | None = None,
        delay: float = 1.0,
        force: bool = False,
    ) -> ContestCrawlResult:
        effective_max_pages = max_pages if max_pages is not None else settings.contest_crawl_max_pages
        effective_start_page = start_page if start_page is not None else 1
        _ensure_playwright_ready()
        if sys.platform == "win32":
            stats = await asyncio.to_thread(
                _run_crawl_in_proactor_thread,
                max_pages=effective_max_pages,
                start_page=effective_start_page,
                limit=limit,
                delay=delay,
                force=force,
            )
        else:
            stats = await run_crawl(
                max_pages=effective_max_pages,
                start_page=effective_start_page,
                limit=limit,
                delay=delay,
                force=force,
            )
        hint = (
            f"{stats['new_count']}건 신규 저장 (목록 page {effective_start_page}"
            f"~{effective_start_page + effective_max_pages - 1}). "
            f"다음: POST /contest-admin/sync 또는 POST /contest-pins/cardnews"
        )
        if stats["errors"]:
            hint = f"일부 오류 발생({stats['errors']}건). " + hint
        return ContestCrawlResult(
            saved_documents_path=stats["saved_documents_path"],
            new_count=stats["new_count"],
            skipped_expired=stats["skipped_expired"],
            skipped_duplicate=stats["skipped_duplicate"],
            errors=stats["errors"],
            total_count=stats["total_count"],
            start_page=effective_start_page,
            max_pages=effective_max_pages,
            hint=hint,
        )

    def load_documents_from_jsonl(
        self,
        *,
        file_path: Path | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        contentid: str | None = None,
    ) -> ContestDocumentsListResult:
        path = file_path or self.documents_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"원문 JSONL 없음: {path}. "
                "POST /contest-pins/crawl 또는 fetch_linkareer_contests 스크립트를 먼저 실행하세요.",
            )

        effective_limit = _MAX_LIST_ITEMS if limit is None else min(limit, _MAX_LIST_ITEMS)
        use_date_filter = start_date is not None and end_date is not None
        cid_filter = (contentid or "").strip()

        matched: list[ContestDocumentDTO] = []
        total_in_file = 0

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total_in_file += 1
                row = normalize_contest_row(json.loads(line))
                try:
                    item = ContestDocumentDTO.model_validate(row)
                except ValidationError as exc:
                    raise ValueError(
                        f"JSONL 형식 오류 (line {total_in_file}, contentid={row.get('contentid')}): {exc}"
                    ) from exc

                if cid_filter and item.contentid != cid_filter:
                    continue

                if use_date_filter and not festival_overlaps_range(
                    event_start=item.event_start_time,
                    event_end=item.event_end_time,
                    query_start=start_date,
                    query_end=end_date,
                ):
                    continue

                matched.append(item)

        documents = matched[:effective_limit]

        hint: str | None = None
        if total_in_file == 0:
            hint = "JSONL이 비어 있습니다. POST /contest-pins/crawl 을 실행하세요."
        elif len(documents) == 0:
            if cid_filter:
                hint = f"contentid={cid_filter} 에 해당하는 공모전이 없습니다."
            elif use_date_filter:
                hint = "기간 필터에 맞는 공모전이 없습니다. start_date/end_date를 비우세요."
            else:
                hint = "조회 결과가 없습니다."

        return ContestDocumentsListResult(
            filter_start_date=start_date,
            filter_end_date=end_date,
            saved_documents_path=str(path),
            total_in_file=total_in_file,
            matched_count=len(matched),
            count=len(documents),
            documents=documents,
            hint=hint,
        )

    async def transform_and_save(
        self,
        *,
        limit: int | None = None,
        model: str | None = None,
        s3_util: S3Util | None = None,
        db_contest_api_ids: set[int] | None = None,
        with_caption: bool = True,
        contentid: str | None = None,
    ) -> ContestPinTransformResult:
        return await transform_documents_jsonl(
            limit=limit,
            model=model,
            s3_util=s3_util,
            db_contest_api_ids=db_contest_api_ids,
            merge_handoff=True,
            with_caption=with_caption,
            contentid=contentid,
        )

    async def cardnews_and_save(
        self,
        *,
        limit: int | None = None,
        model: str | None = None,
        s3_util: S3Util | None = None,
        db_contest_api_ids: set[int] | None = None,
        with_caption: bool = True,
        contentid: str | None = None,
    ) -> ContestPinTransformResult:
        return await self.transform_and_save(
            limit=limit,
            model=model,
            s3_util=s3_util,
            db_contest_api_ids=db_contest_api_ids,
            with_caption=with_caption,
            contentid=contentid,
        )

    async def transform_batch(
        self,
        *,
        batch_size: int | None = None,
        model: str | None = None,
        s3_util: S3Util | None = None,
        db_contest_api_ids: set[int] | None = None,
    ) -> ContestTransformBatchResult:
        size = batch_size or settings.contest_sync_batch_size
        result = await self.transform_and_save(
            limit=size,
            model=model,
            s3_util=s3_util,
            db_contest_api_ids=db_contest_api_ids,
        )
        return ContestTransformBatchResult(
            **result.model_dump(),
            requested_batch_size=size,
            batches_run=1,
        )

    async def sync_pipeline(
        self,
        *,
        ingest_service: ContestEventIngestService,
        s3_util: S3Util,
        transform_limit: int | None = None,
        batch_size: int | None = None,
        max_pages: int | None = None,
        start_page: int | None = None,
    ) -> ContestSyncResult:
        effective_batch = batch_size or settings.contest_sync_batch_size

        if settings.contest_prune_pipeline_after_import:
            db_ids_before = await ingest_service.get_imported_contest_api_ids()
            prune_pipeline_imported(db_ids_before)

        crawl = await self.crawl_and_save(
            max_pages=max_pages,
            start_page=start_page,
            force=False,
        )

        total_processed = 0
        total_imported = 0
        total_skipped_import = 0
        total_skipped_transform = 0
        transform_errors: list[dict] = []
        transform_pins: list = []
        import_errors: list[dict] = []
        import_items: list[ContestBatchItemResult] = []
        import_pin_ids: list[int] = []
        batches_run = 0
        last_transform_pending = 0
        last_import = ContestImportBatchResult(
            inserted_count=0,
            skipped_duplicate_count=0,
            pending_import_count=0,
            error_count=0,
        )

        def _accumulate_import(import_batch: ContestImportBatchResult) -> None:
            nonlocal total_imported, total_skipped_import, last_import
            total_imported += import_batch.inserted_count
            total_skipped_import += import_batch.skipped_duplicate_count
            import_errors.extend(import_batch.errors)
            import_items.extend(import_batch.items)
            import_pin_ids.extend(import_batch.pin_ids)
            last_import = import_batch

        db_ids = await ingest_service.get_imported_contest_api_ids()

        def _track_imported_ids(import_batch: ContestImportBatchResult) -> None:
            for item in import_batch.items:
                if item.action == ContestBatchAction.CREATED and item.contest_api_id is not None:
                    db_ids.add(item.contest_api_id)

        while True:
            if transform_limit is not None and total_processed >= transform_limit:
                break

            batch_limit = effective_batch
            if transform_limit is not None:
                batch_limit = min(effective_batch, transform_limit - total_processed)

            transform_batch = await self.transform_and_save(
                limit=batch_limit,
                s3_util=s3_util,
                db_contest_api_ids=db_ids,
            )
            batches_run += 1
            total_processed += transform_batch.processed_count
            total_skipped_transform += transform_batch.skipped_duplicate_count
            transform_errors.extend(transform_batch.errors)
            transform_pins.extend(transform_batch.pins)
            last_transform_pending = transform_batch.remaining_pending_count

            if transform_batch.processed_count > 0:
                import_batch = await ingest_service.import_handoff_batch(
                    import_all=False,
                    limit=effective_batch,
                )
                _accumulate_import(import_batch)
                _track_imported_ids(import_batch)

            if transform_batch.remaining_pending_count == 0:
                break
            if transform_batch.processed_count == 0:
                break

        while load_jsonl_rows(self.handoff_path()):
            prev_pending = last_import.pending_import_count
            import_batch = await ingest_service.import_handoff_batch(
                import_all=False,
                limit=effective_batch,
            )
            _accumulate_import(import_batch)
            _track_imported_ids(import_batch)
            if import_batch.pending_import_count == 0:
                break
            if import_batch.inserted_count == 0 and import_batch.pending_import_count >= prev_pending:
                break

        aggregated_transform = ContestTransformBatchResult(
            input_path=str(self.documents_path()),
            output_path=str(self.handoff_path()),
            processed_count=total_processed,
            error_count=len(transform_errors),
            errors=transform_errors,
            pins=transform_pins,
            hint=(
                f"배치 {batches_run}회, 가공 {total_processed}건 "
                f"(배치 크기 {effective_batch}, 동시성 {settings.contest_transform_concurrency})"
            ),
            skipped_duplicate_count=total_skipped_transform,
            pending_count=last_transform_pending,
            remaining_pending_count=last_transform_pending,
            requested_batch_size=effective_batch,
            batches_run=batches_run,
        )
        import_result = ContestImportBatchResult(
            inserted_count=total_imported,
            skipped_duplicate_count=total_skipped_import,
            pending_import_count=last_import.pending_import_count,
            error_count=len(import_errors),
            errors=import_errors,
            items=import_items,
            pin_ids=import_pin_ids,
            requested_batch_size=effective_batch,
        )

        ContestEventIngestService.write_sync_meta()
        hint = (
            f"sync 완료: 크롤 신규 {crawl.new_count}건, 가공 {total_processed}건({batches_run}배치), "
            f"DB INSERT {total_imported}건."
        )
        if (
            total_processed == 0
            and total_imported == 0
            and last_transform_pending == 0
            and len(db_ids) > 0
        ):
            hint = (
                f"이미 DB 반영 완료 (contest 핀 {len(db_ids)}건). "
                "handoff JSONL이 비어 있는 것은 import 후 캐시 정리로 정상입니다."
            )
        elif total_processed == 0 and last_transform_pending > 0:
            hint = (
                f"크롤 신규 {crawl.new_count}건 저장됐으나 가공 0건입니다. "
                f"미가공 {last_transform_pending}건 — GEMINI_API_KEY·transform 오류를 확인하세요."
            )
        elif total_processed > 0 and last_transform_pending > 0:
            hint = (
                f"sync 부분 완료: 가공 {total_processed}건, DB INSERT {total_imported}건. "
                f"미가공 {last_transform_pending}건 남음 — /contest-admin/sync 재실행 또는 transform-batch."
            )

        return ContestSyncResult(
            crawl=crawl,
            transform=aggregated_transform,
            import_result=import_result,
            hint=hint,
        )

    def load_handoff_from_jsonl(
        self,
        *,
        limit: int | None = None,
    ) -> ContestPinHandoffResult:
        path, pins, total_in_file = load_handoff_from_jsonl(limit=limit)
        hint: str | None = None
        if total_in_file == 0:
            hint = "JSONL이 비어 있습니다. POST /contest-pins/cardnews 를 먼저 실행하세요."
        return ContestPinHandoffResult(
            output_path=str(path),
            total_in_file=total_in_file,
            count=len(pins),
            pins=pins,
            hint=hint,
        )
