from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.codes import ErrorCode, SuccessCode
from app.core.config import settings
from app.core.deps import AdminUserIdDep, FestivalEventIngestServiceDep
from app.core.responses import SuccessEnvelope, success_response
from app.schemas.FestivalAdminDTO import (
    FestivalFetchResult,
    FestivalImportBatchResult,
    FestivalPipelineResetResult,
    FestivalPipelineStatusResult,
    FestivalTransformBatchResult,
)
from app.schemas.FestivalPinDTO import FestivalPinHandoffResult
from app.utils.festival_date_filter import current_year_festival_range, validate_yyyymmdd
from app.utils.visitkorea_area import TOURAPI_AREA_NAMES, validate_area_code, validate_sigungu_code

router = APIRouter(prefix="/festival-admin", tags=["festival-admin"])

_DEFAULT_BATCH = settings.festival_batch_size
_MAX_BATCH = 50
_ALLOWED_PAGE_SIZES = {5, 25}


def _resolve_fetch_limit(value: int | None) -> int | None:
    if value is None:
        return None
    return min(max(value, 1), _MAX_BATCH)


def _resolve_page_size(value: int | None) -> int:
    if value is None:
        return 25
    if value not in _ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail="page_size는 5 또는 25만 허용됩니다.",
        )
    return value


def _resolve_transform_batch_size(value: int | None, page_size: int) -> int | None:
    if value is None:
        return None
    if value not in _ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail="batch_size는 5 또는 25만 허용됩니다.",
        )
    return value


def _runtime_error_response(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if "GEMINI" in detail or "VISITKOREA" in detail:
        status = ErrorCode.VLM_NOT_CONFIGURED.http_status
    else:
        status = ErrorCode.INTERNAL_SERVER_ERROR.http_status
    return HTTPException(status_code=status, detail=detail)


def _parse_area_filters(
    area_code: str | None,
    sigungu_code: str | None,
) -> tuple[str | None, str | None]:
    try:
        parsed_area = validate_area_code(area_code)
        parsed_sigungu = validate_sigungu_code(sigungu_code, area_code=parsed_area)
    except ValueError as exc:
        raise HTTPException(status_code=ErrorCode.BAD_REQUEST.http_status, detail=str(exc)) from exc
    return parsed_area, parsed_sigungu


def _clamp_batch(value: int | None) -> int:
    if value is None:
        return _DEFAULT_BATCH
    return min(max(value, 1), _MAX_BATCH)


@router.get(
    "/areas",
    summary="TourAPI 시·도 areaCode 목록",
)
async def list_festival_area_codes(
    _admin_uid: AdminUserIdDep,
) -> SuccessEnvelope[list[dict[str, str]]]:
    areas = [
        {"area_code": code, "area_name": name}
        for code, name in sorted(TOURAPI_AREA_NAMES.items(), key=lambda item: int(item[0]))
    ]
    return success_response(result=areas, success_code=SuccessCode.FESTIVAL_STATUS_SUCCESS)


@router.post(
    "/fetch-year",
    response_model=SuccessEnvelope[FestivalFetchResult],
    summary="올해 축제 수집 (오늘~12/31, area_code로 지역 제한 가능)",
)
async def fetch_festivals_year(
    _admin_uid: AdminUserIdDep,
    service: FestivalEventIngestServiceDep,
    area_code: str | None = Query(default=None, description="TourAPI 시·도 코드 (예: 1=서울)"),
    sigungu_code: str | None = Query(default=None, description="TourAPI 시·군·구 코드"),
) -> SuccessEnvelope[FestivalFetchResult]:
    parsed_area, parsed_sigungu = _parse_area_filters(area_code, sigungu_code)
    try:
        body = await service.fetch_year_and_save(
            area_code=parsed_area,
            sigungu_code=parsed_sigungu,
        )
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc
    return success_response(result=body, success_code=SuccessCode.FESTIVAL_FETCH_SUCCESS)


@router.post(
    "/fetch",
    response_model=SuccessEnvelope[FestivalFetchResult],
    summary="TourAPI 수집 (limit 생략 시 기간 내 신규 전체 merge)",
)
async def fetch_festivals(
    _admin_uid: AdminUserIdDep,
    service: FestivalEventIngestServiceDep,
    start_date: str | None = Query(default=None, min_length=8, max_length=8),
    end_date: str | None = Query(default=None, min_length=8, max_length=8),
    limit: int | None = Query(default=None, ge=1, le=_MAX_BATCH),
    area_code: str | None = Query(default=None, description="TourAPI 시·도 코드 (예: 1=서울)"),
    sigungu_code: str | None = Query(default=None, description="TourAPI 시·군·구 코드"),
) -> SuccessEnvelope[FestivalFetchResult]:
    parsed_area, parsed_sigungu = _parse_area_filters(area_code, sigungu_code)
    if start_date is None and end_date is None:
        parsed_start, parsed_end = current_year_festival_range()
    elif start_date is not None and end_date is not None:
        try:
            parsed_start = validate_yyyymmdd(start_date, label="start_date")
            parsed_end = validate_yyyymmdd(end_date, label="end_date")
        except ValueError as exc:
            raise HTTPException(status_code=ErrorCode.BAD_REQUEST.http_status, detail=str(exc)) from exc
    else:
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail="start_date와 end_date는 함께 지정하거나 둘 다 생략해야 합니다.",
        )
    if parsed_start > parsed_end:
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail="start_date는 end_date보다 이후일 수 없습니다.",
        )
    try:
        body = await service.fetch_and_save(
            start_date=parsed_start,
            end_date=parsed_end,
            limit=_resolve_fetch_limit(limit),
            area_code=parsed_area,
            sigungu_code=parsed_sigungu,
        )
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc
    return success_response(result=body, success_code=SuccessCode.FESTIVAL_FETCH_SUCCESS)


@router.post(
    "/transform-batch",
    response_model=SuccessEnvelope[FestivalTransformBatchResult],
    summary="LLM 페이지 가공 (pending을 page_size 단위, batch_size는 5 또는 25)",
)
async def transform_festival_batch(
    _admin_uid: AdminUserIdDep,
    service: FestivalEventIngestServiceDep,
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=25, ge=5, le=25),
    batch_size: int | None = Query(default=None, ge=5, le=25),
    area_code: str | None = Query(default=None, description="documents/handoff 지역 필터"),
    sigungu_code: str | None = Query(default=None, description="시·군·구 필터 (area_code와 함께)"),
) -> SuccessEnvelope[FestivalTransformBatchResult]:
    parsed_area, parsed_sigungu = _parse_area_filters(area_code, sigungu_code)
    resolved_page_size = _resolve_page_size(page_size)
    resolved_batch_size = _resolve_transform_batch_size(batch_size, resolved_page_size)
    try:
        body = await service.transform_batch(
            batch_size=resolved_batch_size,
            page=page,
            page_size=resolved_page_size,
            area_code=parsed_area,
            sigungu_code=parsed_sigungu,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=ErrorCode.BAD_REQUEST.http_status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc
    return success_response(result=body, success_code=SuccessCode.FESTIVAL_TRANSFORM_BATCH_SUCCESS)


@router.get(
    "/handoff",
    response_model=SuccessEnvelope[FestivalPinHandoffResult],
    summary="handoff JSONL 미리보기",
)
async def preview_festival_handoff(
    _admin_uid: AdminUserIdDep,
    service: FestivalEventIngestServiceDep,
    start_date: str | None = Query(default=None, min_length=8, max_length=8),
    end_date: str | None = Query(default=None, min_length=8, max_length=8),
    limit: int | None = Query(default=None, ge=1, le=500),
) -> SuccessEnvelope[FestivalPinHandoffResult]:
    if (start_date is None) ^ (end_date is None):
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail="start_date와 end_date는 함께 지정하거나 둘 다 생략해야 합니다.",
        )
    parsed_start: str | None = None
    parsed_end: str | None = None
    if start_date is not None and end_date is not None:
        try:
            parsed_start = validate_yyyymmdd(start_date, label="start_date")
            parsed_end = validate_yyyymmdd(end_date, label="end_date")
        except ValueError as exc:
            raise HTTPException(status_code=ErrorCode.BAD_REQUEST.http_status, detail=str(exc)) from exc
    try:
        body = service.load_handoff_preview(
            start_date=parsed_start,
            end_date=parsed_end,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    return success_response(result=body, success_code=SuccessCode.FESTIVAL_HANDOFF_SUCCESS)


@router.post(
    "/import-batch",
    response_model=SuccessEnvelope[FestivalImportBatchResult],
    summary="DB 배치 적재 (미적재 batch_size건 INSERT, allow_update 시 갱신)",
)
async def import_festival_batch(
    admin_uid: AdminUserIdDep,
    service: FestivalEventIngestServiceDep,
    batch_size: int | None = Query(default=None, ge=1, le=_MAX_BATCH),
    allow_update: bool = Query(default=False),
    area_code: str | None = Query(default=None, description="handoff 지역 필터"),
    sigungu_code: str | None = Query(default=None),
) -> SuccessEnvelope[FestivalImportBatchResult]:
    parsed_area, parsed_sigungu = _parse_area_filters(area_code, sigungu_code)
    try:
        body = await service.import_batch(
            admin_uid=admin_uid,
            batch_size=_clamp_batch(batch_size),
            allow_update=allow_update,
            area_code=parsed_area,
            sigungu_code=parsed_sigungu,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except Exception:
        await service.rollback()
        raise
    return success_response(result=body, success_code=SuccessCode.FESTIVAL_IMPORT_BATCH_SUCCESS)


@router.post(
    "/import-all",
    response_model=SuccessEnvelope[FestivalImportBatchResult],
    summary="DB 일괄 적재 (미적재 handoff 전체 INSERT, allow_update 시 갱신)",
)
async def import_festival_all(
    admin_uid: AdminUserIdDep,
    service: FestivalEventIngestServiceDep,
    allow_update: bool = Query(default=False),
    area_code: str | None = Query(default=None, description="handoff 지역 필터"),
    sigungu_code: str | None = Query(default=None),
) -> SuccessEnvelope[FestivalImportBatchResult]:
    parsed_area, parsed_sigungu = _parse_area_filters(area_code, sigungu_code)
    try:
        body = await service.import_all(
            admin_uid=admin_uid,
            allow_update=allow_update,
            area_code=parsed_area,
            sigungu_code=parsed_sigungu,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=ErrorCode.NOT_FOUND.http_status, detail=str(exc)) from exc
    except Exception:
        await service.rollback()
        raise
    return success_response(result=body, success_code=SuccessCode.FESTIVAL_IMPORT_ALL_SUCCESS)


@router.post(
    "/reset",
    response_model=SuccessEnvelope[FestivalPipelineResetResult],
    summary="중복 제거용 로컬 JSON 캐시 초기화 (documents/handoff/meta 등 삭제)",
)
async def reset_festival_pipeline_cache(
    _admin_uid: AdminUserIdDep,
    service: FestivalEventIngestServiceDep,
) -> SuccessEnvelope[FestivalPipelineResetResult]:
    body = service.reset_dedup_cache()
    return success_response(result=body, success_code=SuccessCode.FESTIVAL_RESET_SUCCESS)


@router.get(
    "/status",
    response_model=SuccessEnvelope[FestivalPipelineStatusResult],
    summary="파이프라인 진행 상태 (side effect 없음)",
)
async def festival_pipeline_status(
    _admin_uid: AdminUserIdDep,
    service: FestivalEventIngestServiceDep,
) -> SuccessEnvelope[FestivalPipelineStatusResult]:
    body = await service.get_pipeline_status()
    return success_response(result=body, success_code=SuccessCode.FESTIVAL_STATUS_SUCCESS)
