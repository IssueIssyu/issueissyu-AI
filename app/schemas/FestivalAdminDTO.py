from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.FestivalPinDTO import FestivalPinDTO


class FestivalBatchAction(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"


class FestivalBatchItemResult(BaseModel):
    festival_api_id: int | None = None
    pin_title: str | None = None
    action: FestivalBatchAction
    message: str | None = None


class FestivalFetchResult(BaseModel):
    query_start_date: str
    query_end_date: str
    requested_limit: int | None = Field(
        default=None,
        description="None이면 기간 내 신규 전체 수집",
    )
    area_code: str | None = Field(default=None, description="TourAPI 시·도 코드 (예: 1=서울, 31=경기)")
    sigungu_code: str | None = Field(default=None, description="TourAPI 시·군·구 코드 (area_code와 함께)")
    area_name: str | None = Field(default=None, description="시·도명")
    tourapi_total_count: int
    added_count: int
    skipped_duplicate_count: int
    skipped_area_count: int = Field(default=0, description="지역 필터로 제외된 건수")
    total_in_documents: int
    pending_transform_count: int
    saved_documents_path: str
    pins: list[dict[str, Any]] = Field(default_factory=list)


class FestivalTransformBatchResult(BaseModel):
    page: int = Field(description="1-based 페이지")
    page_size: int = Field(description="페이지당 처리 상한 (5 또는 25)")
    total_pages: int = Field(description="pending 기준 전체 페이지 수")
    total_pending_before_page: int = Field(description="가공 대기 전체 건수")
    requested_batch_size: int
    area_code: str | None = None
    sigungu_code: str | None = None
    area_name: str | None = None
    processed_count: int
    skipped_duplicate_count: int
    pending_transform_count: int
    error_count: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    items: list[FestivalBatchItemResult] = Field(default_factory=list)
    pins: list[FestivalPinDTO] = Field(default_factory=list)
    output_path: str


class FestivalImportBatchResult(BaseModel):
    requested_batch_size: int | None = Field(
        default=None,
        description="None이면 handoff 전체 일괄 적재",
    )
    import_all: bool = Field(default=False, description="True면 미적재 handoff 전체 INSERT")
    area_code: str | None = None
    sigungu_code: str | None = None
    area_name: str | None = None
    inserted_count: int
    updated_count: int
    skipped_duplicate_count: int
    pending_import_count: int
    error_count: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    items: list[FestivalBatchItemResult] = Field(default_factory=list)
    pin_ids: list[int] = Field(default_factory=list)


class FestivalPipelineStatusResult(BaseModel):
    tourapi_total_count: int | None = None
    query_start_date: str | None = None
    query_end_date: str | None = None
    area_code: str | None = None
    sigungu_code: str | None = None
    area_name: str | None = None
    documents_count: int
    handoff_count: int
    db_festival_count: int
    pending_transform_count: int
    pending_import_count: int


class FestivalPipelineResetResult(BaseModel):
    deleted_files: list[str] = Field(default_factory=list)
    note: str = Field(
        default="DB event_pin.festival_api_id는 유지됩니다. import 중복 스킵까지 초기화하려면 DB에서 축제 pin을 삭제하세요.",
    )


class FestivalDbReadyPinDTO(FestivalPinDTO):
    festival_api_id: int | None = Field(default=None, description="TourAPI contentid (DB event_pin.festival_api_id)")
