from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.codes import ErrorCode, SuccessCode
from app.core.config import settings
from app.core.deps import (
    PolicyEventIngestServiceDep,
    PolicyPinSchedulerDep,
    PolicyPinServiceDep,
    S3UtilDep,
)
from app.core.responses import SuccessEnvelope, success_response
from app.schemas.PolicyAdminDTO import (
    PolicyImportBatchResult,
    PolicyPipelineStatusResult,
    PolicySyncResult,
    PolicyTransformBatchResult,
)

router = APIRouter(prefix="/policy-admin", tags=["policy-admin"])

_MAX_BATCH = 25


def _runtime_error_response(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if "GEMINI" in detail or "POLICY" in detail or "S3" in detail:
        status = ErrorCode.VLM_NOT_CONFIGURED.http_status
    else:
        status = ErrorCode.INTERNAL_SERVER_ERROR.http_status
    return HTTPException(status_code=status, detail=detail)


def _clamp_batch(value: int | None) -> int:
    if value is None:
        return settings.policy_sync_batch_size
    return min(max(value, 1), _MAX_BATCH)


@router.post(
    "/sync",
    response_model=SuccessEnvelope[PolicySyncResult],
    summary="정책 핀 3일 lookback 수집 → 배치 transform → 배치 DB 적재",
    description=(
        "오늘 포함 최근 POLICY_SYNC_LOOKBACK_DAYS(기본 3일) 구간을 수집하고, "
        "신규 NewsItemId만 POLICY_SYNC_BATCH_SIZE 단위로 LLM 가공·DB INSERT합니다."
    ),
)
async def sync_policy_pins(
    service: PolicyPinServiceDep,
    ingest_service: PolicyEventIngestServiceDep,
    s3_util: S3UtilDep,
    start_date: str | None = Query(default=None, min_length=8, max_length=8, description="YYYYMMDD"),
    end_date: str | None = Query(default=None, min_length=8, max_length=8, description="YYYYMMDD"),
    transform_limit: int | None = Query(default=None, ge=1, le=100, description="가공 최대 건수"),
    batch_size: int | None = Query(default=None, ge=1, le=25, description="배치 크기"),
) -> SuccessEnvelope[PolicySyncResult]:
    try:
        body = await service.sync_pipeline(
            ingest_service=ingest_service,
            s3_util=s3_util,
            start_date=start_date,
            end_date=end_date,
            transform_limit=transform_limit,
            batch_size=_clamp_batch(batch_size),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.CREATED)


@router.post(
    "/transform-batch",
    response_model=SuccessEnvelope[PolicyTransformBatchResult],
    summary="원문 JSONL 배치 가공 (신규 건만)",
)
async def transform_policy_batch(
    service: PolicyPinServiceDep,
    ingest_service: PolicyEventIngestServiceDep,
    s3_util: S3UtilDep,
    batch_size: int | None = Query(default=None, ge=1, le=25, description="이번 배치 가공 건수"),
) -> SuccessEnvelope[PolicyTransformBatchResult]:
    try:
        db_ids = await ingest_service._event_pin_repo.list_policy_api_ids()
        body = await service.transform_batch(
            batch_size=_clamp_batch(batch_size),
            s3_util=s3_util,
            db_policy_api_ids=db_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.CREATED)


@router.post(
    "/import-batch",
    response_model=SuccessEnvelope[PolicyImportBatchResult],
    summary="handoff JSONL 배치 DB 적재",
)
async def import_policy_batch(
    ingest_service: PolicyEventIngestServiceDep,
    batch_size: int | None = Query(default=None, ge=1, le=25, description="이번 배치 INSERT 건수"),
) -> SuccessEnvelope[PolicyImportBatchResult]:
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
    response_model=SuccessEnvelope[PolicyPipelineStatusResult],
    summary="정책 핀 파이프라인 상태",
)
async def policy_pipeline_status(
    ingest_service: PolicyEventIngestServiceDep,
) -> SuccessEnvelope[PolicyPipelineStatusResult]:
    body = await ingest_service.get_pipeline_status()
    return success_response(result=body, success_code=SuccessCode.OK)


@router.post(
    "/scheduler/run-once",
    response_model=SuccessEnvelope[PolicySyncResult],
    summary="정책 핀 스케줄러 즉시 1회 실행 (테스트용, 간격 무시)",
)
async def run_policy_scheduler_once(
    service: PolicyPinServiceDep,
    ingest_service: PolicyEventIngestServiceDep,
    s3_util: S3UtilDep,
    scheduler: PolicyPinSchedulerDep,
) -> SuccessEnvelope[PolicySyncResult]:
    try:
        if scheduler is not None:
            body = await scheduler.run_once_now(force=True)
        else:
            body = await service.sync_pipeline(
                ingest_service=ingest_service,
                s3_util=s3_util,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.CREATED)
