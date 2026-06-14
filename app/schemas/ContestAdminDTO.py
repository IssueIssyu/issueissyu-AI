from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.ContestPinDTO import ContestCrawlResult, ContestPinTransformResult


class ContestBatchAction(str, Enum):
    CREATED = "created"
    SKIPPED = "skipped"
    ERROR = "error"


class ContestBatchItemResult(BaseModel):
    contest_api_id: int | None = None
    pin_title: str | None = None
    action: ContestBatchAction
    message: str | None = None


class ContestImportBatchResult(BaseModel):
    inserted_count: int
    skipped_duplicate_count: int
    skipped_expired_count: int = 0
    pending_import_count: int
    error_count: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    items: list[ContestBatchItemResult] = Field(default_factory=list)
    pin_ids: list[int] = Field(default_factory=list)
    requested_batch_size: int | None = None
    hint: str | None = None


class ContestTransformBatchResult(ContestPinTransformResult):
    requested_batch_size: int | None = None
    batches_run: int = 1


class ContestPipelineStatusResult(BaseModel):
    last_sync_at: str | None = None
    documents_count: int
    handoff_count: int
    db_contest_count: int
    pending_transform_count: int
    pending_import_count: int
    is_caught_up: bool = Field(
        default=False,
        description="미가공·미적재 건이 없어 DB와 파이프라인이 동기화된 상태",
    )
    hint: str | None = None


class ContestSyncResult(BaseModel):
    crawl: ContestCrawlResult
    transform: ContestTransformBatchResult
    import_result: ContestImportBatchResult
    hint: str | None = None
