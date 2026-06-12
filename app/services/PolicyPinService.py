from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.clients.PolicyNewsClient import PolicyNewsClient
from app.core.config import settings
from app.schemas.PolicyAdminDTO import (
    PolicyBatchItemResult,
    PolicyImportBatchResult,
    PolicySyncResult,
    PolicyTransformBatchResult,
)
from app.schemas.PolicyPinDTO import (
    PolicyPinHandoffDTO,
    PolicyPinHandoffResult,
    PolicyPinSearchResult,
    PolicyPinSourceDTO,
    PolicyPinTransformResult,
)
from app.services.PolicyEventIngestService import PolicyEventIngestService
from app.services.policy_pipeline_cleanup import prune_pipeline_imported
from app.services.policy_pin_transform import (
    POLICY_DOCUMENTS_PATH,
    POLICY_HANDOFF_PATH,
    load_rows_by_content_id,
    merge_documents,
    transform_documents_jsonl,
)
from app.utils.S3Util import S3Util
from rag.scripts.chunk_module import write_jsonl
from rag.scripts.fetch_policy_news import fetch_policy_documents

_MAX_HANDOFF_ITEMS = 500


async def _enrich_cover_image_urls(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.utils.policy_news_parse import enrich_cover_image_urls as resolve_cover_image_urls

    async def enrich_one(doc: dict[str, Any]) -> dict[str, Any]:
        row = dict(doc)
        if row.get("image_urls"):
            return row
        urls = await resolve_cover_image_urls([], source_url=str(row.get("source_url") or ""))
        if urls:
            row["original_image_urls"] = urls[:1]
            row["image_urls"] = urls
        return row

    return list(await asyncio.gather(*(enrich_one(doc) for doc in documents)))


class PolicyPinService:
    @staticmethod
    def documents_path() -> Path:
        return POLICY_DOCUMENTS_PATH

    @staticmethod
    def handoff_path() -> Path:
        return POLICY_HANDOFF_PATH

    async def search_and_save(
        self,
        *,
        start_date: str,
        end_date: str,
        limit: int | None = 10,
        merge: bool = True,
    ) -> PolicyPinSearchResult:
        fetch_limit: int | None
        if limit is None:
            fetch_limit = None
        else:
            fetch_limit = min(max(limit, 1), 50)

        async with PolicyNewsClient.from_settings() as client:
            documents, stats = await fetch_policy_documents(
                client=client,
                start_date=start_date,
                end_date=end_date,
                limit=fetch_limit,
            )

        documents = await _enrich_cover_image_urls(documents)

        path = self.documents_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if merge:
            existing = load_rows_by_content_id(path)
            merged = merge_documents(existing, documents)
            write_jsonl(path, merged)
            total_in_file = len(merged)
        else:
            write_jsonl(path, documents)
            total_in_file = len(documents)

        pins = [PolicyPinSourceDTO.model_validate(doc) for doc in documents]
        hint: str | None
        if len(pins) == 0:
            hint = (
                f"수집 0건 (API 호출 {stats.get('chunks', 0)}회). "
                "정책뉴스 API는 승인일 기준이며 미래 날짜 구간은 비어 있습니다. "
                f"JSONL 총 {total_in_file}건 유지."
            )
        else:
            hint = (
                f"이번 수집 {len(pins)}건, {path.name} 총 {total_in_file}건. "
                "다음: POST /policy-pins/transform 또는 /policy-admin/sync"
            )
        return PolicyPinSearchResult(
            query_start_date=start_date,
            query_end_date=end_date,
            count=len(pins),
            pins=pins,
            saved_documents_path=str(path),
            stats={k: int(v) for k, v in stats.items()},
            hint=hint,
        )

    async def transform_and_save(
        self,
        *,
        limit: int | None = None,
        model: str | None = None,
        s3_util: S3Util | None = None,
        db_policy_api_ids: set[int] | None = None,
    ) -> PolicyPinTransformResult:
        return await transform_documents_jsonl(
            limit=limit,
            model=model,
            s3_util=s3_util,
            db_policy_api_ids=db_policy_api_ids,
            merge_handoff=True,
        )

    async def transform_batch(
        self,
        *,
        batch_size: int | None = None,
        model: str | None = None,
        s3_util: S3Util | None = None,
        db_policy_api_ids: set[int] | None = None,
    ) -> PolicyTransformBatchResult:
        size = batch_size or settings.policy_sync_batch_size
        result = await self.transform_and_save(
            limit=size,
            model=model,
            s3_util=s3_util,
            db_policy_api_ids=db_policy_api_ids,
        )
        return PolicyTransformBatchResult(
            **result.model_dump(),
            requested_batch_size=size,
            batches_run=1,
        )

    async def sync_pipeline(
        self,
        *,
        ingest_service: PolicyEventIngestService,
        s3_util: S3Util,
        start_date: str | None = None,
        end_date: str | None = None,
        transform_limit: int | None = None,
        batch_size: int | None = None,
    ) -> PolicySyncResult:
        if start_date is None or end_date is None:
            start_date, end_date = self.default_date_range()

        effective_batch = batch_size or settings.policy_sync_batch_size

        if settings.policy_prune_pipeline_after_import:
            db_ids_before = await ingest_service.get_imported_policy_api_ids()
            prune_pipeline_imported(db_ids_before)

        search = await self.search_and_save(
            start_date=start_date,
            end_date=end_date,
            limit=None,
            merge=settings.policy_sync_merge_documents,
        )

        total_processed = 0
        total_imported = 0
        total_skipped_import = 0
        total_skipped_transform = 0
        transform_errors: list[dict] = []
        transform_pins: list = []
        import_errors: list[dict] = []
        import_items: list[PolicyBatchItemResult] = []
        import_pin_ids: list[int] = []
        batches_run = 0
        last_transform_pending = 0
        last_import = PolicyImportBatchResult(
            inserted_count=0,
            skipped_duplicate_count=0,
            pending_import_count=0,
            error_count=0,
        )

        def _accumulate_import(import_batch: PolicyImportBatchResult) -> None:
            nonlocal total_imported, total_skipped_import, last_import
            total_imported += import_batch.inserted_count
            total_skipped_import += import_batch.skipped_duplicate_count
            import_errors.extend(import_batch.errors)
            import_items.extend(import_batch.items)
            import_pin_ids.extend(import_batch.pin_ids)
            last_import = import_batch

        while True:
            if transform_limit is not None and total_processed >= transform_limit:
                break

            batch_limit = effective_batch
            if transform_limit is not None:
                batch_limit = min(effective_batch, transform_limit - total_processed)

            db_ids = await ingest_service.get_imported_policy_api_ids()
            transform_batch = await self.transform_and_save(
                limit=batch_limit,
                s3_util=s3_util,
                db_policy_api_ids=db_ids,
            )
            batches_run += 1
            total_processed += transform_batch.processed_count
            total_skipped_transform += transform_batch.skipped_duplicate_count
            transform_errors.extend(transform_batch.errors)
            transform_pins.extend(transform_batch.pins)
            last_transform_pending = transform_batch.pending_count

            if transform_batch.processed_count == 0:
                break

            import_batch = await ingest_service.import_handoff_batch(
                import_all=False,
                limit=effective_batch,
            )
            _accumulate_import(import_batch)

            if transform_batch.processed_count < batch_limit:
                break

        while True:
            prev_pending = last_import.pending_import_count
            import_batch = await ingest_service.import_handoff_batch(
                import_all=False,
                limit=effective_batch,
            )
            _accumulate_import(import_batch)
            if import_batch.pending_import_count == 0:
                break
            if import_batch.inserted_count == 0 and import_batch.pending_import_count >= prev_pending:
                break

        aggregated_transform = PolicyTransformBatchResult(
            input_path=str(self.documents_path()),
            output_path=str(self.handoff_path()),
            processed_count=total_processed,
            error_count=len(transform_errors),
            errors=transform_errors,
            pins=transform_pins,
            hint=(
                f"배치 {batches_run}회, 가공 {total_processed}건 "
                f"(배치 크기 {effective_batch}, 동시성 {settings.policy_transform_concurrency})"
            ),
            skipped_duplicate_count=total_skipped_transform,
            pending_count=last_transform_pending,
            requested_batch_size=effective_batch,
            batches_run=batches_run,
        )
        import_result = PolicyImportBatchResult(
            inserted_count=total_imported,
            skipped_duplicate_count=total_skipped_import,
            pending_import_count=last_import.pending_import_count,
            error_count=len(import_errors),
            errors=import_errors,
            items=import_items,
            pin_ids=import_pin_ids,
            requested_batch_size=effective_batch,
        )

        PolicyEventIngestService.write_sync_meta(
            query_start_date=start_date,
            query_end_date=end_date,
        )
        hint = (
            f"sync 완료: 수집 {search.count}건, 가공 {total_processed}건({batches_run}배치), "
            f"DB INSERT {total_imported}건."
        )
        return PolicySyncResult(
            query_start_date=start_date,
            query_end_date=end_date,
            search=search,
            transform=aggregated_transform,
            import_result=import_result,
            hint=hint,
        )

    def load_from_jsonl(
        self,
        *,
        file_path: Path | None = None,
        limit: int | None = None,
    ) -> PolicyPinHandoffResult:
        path = file_path or self.handoff_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"핸드오프 JSONL 없음: {path}. POST /policy-pins/transform 를 먼저 실행하세요.",
            )

        effective_limit = _MAX_HANDOFF_ITEMS if limit is None else min(limit, _MAX_HANDOFF_ITEMS)

        pins: list[PolicyPinHandoffDTO] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                pins.append(PolicyPinHandoffDTO.from_row(json.loads(line)))

        total_in_file = len(pins)
        pins = pins[:effective_limit]

        hint: str | None = None
        if total_in_file == 0:
            hint = "JSONL이 비어 있습니다. GET /search → POST /transform 순서로 실행하세요."

        return PolicyPinHandoffResult(
            output_path=str(path),
            total_in_file=total_in_file,
            count=len(pins),
            pins=pins,
            hint=hint,
        )

    @staticmethod
    def default_date_range() -> tuple[str, str]:
        today = date.today()
        lookback = max(1, settings.policy_sync_lookback_days)
        start = today - timedelta(days=lookback - 1)
        return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")
