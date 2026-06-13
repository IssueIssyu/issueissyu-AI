from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.codes import ErrorCode, SuccessCode
from app.core.config import settings
from app.core.deps import (
    AdminUserIdDep,
    ContestEventIngestServiceDep,
    ContestPinSchedulerDep,
    ContestPinServiceDep,
    S3UtilDep,
)
from app.core.responses import SuccessEnvelope, success_response
from app.schemas.ContestAdminDTO import (
    ContestImportBatchResult,
    ContestPipelineStatusResult,
    ContestSyncResult,
    ContestTransformBatchResult,
)
from app.schemas.ContestPinDTO import ContestCrawlResult

router = APIRouter(prefix="/contest-admin", tags=["contest-admin"])

_MAX_BATCH = 25


def _runtime_error_response(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if "GEMINI" in detail or "S3" in detail:
        status = ErrorCode.VLM_NOT_CONFIGURED.http_status
    else:
        status = ErrorCode.INTERNAL_SERVER_ERROR.http_status
    return HTTPException(status_code=status, detail=detail)


def _clamp_batch(value: int | None) -> int:
    if value is None:
        return settings.contest_sync_batch_size
    return min(max(value, 1), _MAX_BATCH)


@router.post(
    "/sync",
    response_model=SuccessEnvelope[ContestSyncResult],
    summary="공모전 핀 크롤 → 배치 transform → 배치 DB 적재",
    description=(
        "Linkareer 목록을 크롤합니다. "
        "수동 실행 시 start_page·max_pages로 순회 구간을 지정할 수 있습니다 "
        "(미지정 시 CONTEST_CRAWL_MAX_PAGES=1, start_page=1). "
        "신규 contentid만 CONTEST_SYNC_BATCH_SIZE 단위로 LLM 가공·DB INSERT합니다."
    ),
)
async def sync_contest_pins(
    service: ContestPinServiceDep,
    ingest_service: ContestEventIngestServiceDep,
    s3_util: S3UtilDep,
    _admin_uid: AdminUserIdDep,
    start_page: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="목록 시작 페이지 (미지정 시 1)",
    ),
    max_pages: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="시작 페이지부터 순회할 페이지 수 (미지정 시 CONTEST_CRAWL_MAX_PAGES)",
    ),
    transform_limit: int | None = Query(default=None, ge=1, le=100, description="가공 최대 건수"),
    batch_size: int | None = Query(default=None, ge=1, le=25, description="배치 크기"),
) -> SuccessEnvelope[ContestSyncResult]:
    try:
        body = await service.sync_pipeline(
            ingest_service=ingest_service,
            s3_util=s3_util,
            transform_limit=transform_limit,
            batch_size=_clamp_batch(batch_size),
            max_pages=max_pages,
            start_page=start_page,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.CREATED)


@router.post(
    "/crawl",
    response_model=SuccessEnvelope[ContestCrawlResult],
    summary="Linkareer 목록만 크롤 (수동)",
    description="sync 없이 크롤만 실행합니다. start_page·max_pages로 순회 구간을 지정하세요.",
)
async def crawl_contest_pins(
    service: ContestPinServiceDep,
    _admin_uid: AdminUserIdDep,
    start_page: int = Query(default=1, ge=1, le=50, description="목록 시작 페이지 번호"),
    max_pages: int = Query(default=1, ge=1, le=50, description="시작 페이지부터 순회할 페이지 수"),
    limit: int | None = Query(default=None, ge=1, le=100, description="상세 수집 최대 건수"),
    delay: float = Query(default=1.0, ge=0.0, le=10.0, description="요청 간 대기(초)"),
    force: bool = Query(default=False, description="기존 contentid도 재수집"),
) -> SuccessEnvelope[ContestCrawlResult]:
    try:
        body = await service.crawl_and_save(
            max_pages=max_pages,
            start_page=start_page,
            limit=limit,
            delay=delay,
            force=force,
        )
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    code = SuccessCode.CREATED if body.new_count else SuccessCode.OK
    return success_response(result=body, success_code=code)


@router.post(
    "/transform-batch",
    response_model=SuccessEnvelope[ContestTransformBatchResult],
    summary="원문 JSONL 배치 가공 (신규 건만)",
)
async def transform_contest_batch(
    service: ContestPinServiceDep,
    ingest_service: ContestEventIngestServiceDep,
    s3_util: S3UtilDep,
    _admin_uid: AdminUserIdDep,
    batch_size: int | None = Query(default=None, ge=1, le=25, description="이번 배치 가공 건수"),
) -> SuccessEnvelope[ContestTransformBatchResult]:
    try:
        db_ids = await ingest_service.get_imported_contest_api_ids()
        body = await service.transform_batch(
            batch_size=_clamp_batch(batch_size),
            s3_util=s3_util,
            db_contest_api_ids=db_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.CREATED)


@router.post(
    "/import-batch",
    response_model=SuccessEnvelope[ContestImportBatchResult],
    summary="handoff JSONL 배치 DB 적재",
)
async def import_contest_batch(
    ingest_service: ContestEventIngestServiceDep,
    _admin_uid: AdminUserIdDep,
    batch_size: int | None = Query(default=None, ge=1, le=25, description="이번 배치 INSERT 건수"),
) -> SuccessEnvelope[ContestImportBatchResult]:
    try:
        body = await ingest_service.import_handoff_batch(
            import_all=False,
            limit=_clamp_batch(batch_size),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.CREATED)


@router.get(
    "/status",
    response_model=SuccessEnvelope[ContestPipelineStatusResult],
    summary="공모전 핀 파이프라인 상태",
)
async def contest_pipeline_status(
    ingest_service: ContestEventIngestServiceDep,
    _admin_uid: AdminUserIdDep,
) -> SuccessEnvelope[ContestPipelineStatusResult]:
    body = await ingest_service.get_pipeline_status()
    return success_response(result=body, success_code=SuccessCode.OK)


@router.post(
    "/scheduler/run-once",
    response_model=SuccessEnvelope[ContestSyncResult],
    summary="공모전 핀 스케줄러 즉시 1회 실행 (테스트용)",
)
async def run_contest_scheduler_once(
    service: ContestPinServiceDep,
    ingest_service: ContestEventIngestServiceDep,
    s3_util: S3UtilDep,
    scheduler: ContestPinSchedulerDep,
    _admin_uid: AdminUserIdDep,
    start_page: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="목록 시작 페이지 (미지정 시 1)",
    ),
    max_pages: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="시작 페이지부터 순회할 페이지 수 (미지정 시 CONTEST_CRAWL_MAX_PAGES)",
    ),
) -> SuccessEnvelope[ContestSyncResult]:
    try:
        if scheduler is not None:
            body = await scheduler.run_once_now(
                force=True,
                max_pages=max_pages,
                start_page=start_page,
            )
        else:
            body = await service.sync_pipeline(
                ingest_service=ingest_service,
                s3_util=s3_util,
                max_pages=max_pages,
                start_page=start_page,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.CREATED)
