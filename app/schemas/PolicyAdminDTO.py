from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.PolicyPinDTO import PolicyPinHandoffDTO, PolicyPinSearchResult, PolicyPinTransformResult


class PolicyBatchAction(str, Enum):
    CREATED = "created"
    SKIPPED = "skipped"
    ERROR = "error"


class PolicyBatchItemResult(BaseModel):
    policy_api_id: int | None = None
    pin_title: str | None = None
    action: PolicyBatchAction
    message: str | None = None


class PolicyImportBatchResult(BaseModel):
    inserted_count: int
    skipped_duplicate_count: int
    pending_import_count: int
    error_count: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    items: list[PolicyBatchItemResult] = Field(default_factory=list)
    pin_ids: list[int] = Field(default_factory=list)
    requested_batch_size: int | None = None


class PolicyTransformBatchResult(PolicyPinTransformResult):
    requested_batch_size: int | None = None
    batches_run: int = 1


class PolicyPipelineStatusResult(BaseModel):
    query_start_date: str | None = None
    query_end_date: str | None = None
    last_sync_at: str | None = None
    documents_count: int
    handoff_count: int
    db_policy_count: int
    pending_transform_count: int
    pending_import_count: int


class PolicySyncResult(BaseModel):
    query_start_date: str
    query_end_date: str
    search: PolicyPinSearchResult
    transform: PolicyPinTransformResult
    import_result: PolicyImportBatchResult
    hint: str | None = None
