from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.codes import ErrorCode, SuccessCode
from app.core.deps import FestivalPinServiceDep
from app.core.responses import SuccessEnvelope, success_response
from app.schemas.FestivalPinDTO import (
    FestivalPinHandoffResult,
    FestivalPinSearchResult,
    FestivalPinTransformResult,
)
from app.utils.festival_date_filter import validate_yyyymmdd

router = APIRouter(prefix="/festival-pins", tags=["festival-pins"])


def _runtime_error_response(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if "GEMINI" in detail or "VISITKOREA" in detail:
        status = ErrorCode.VLM_NOT_CONFIGURED.http_status
    else:
        status = ErrorCode.INTERNAL_SERVER_ERROR.http_status
    return HTTPException(status_code=status, detail=detail)


@router.get(
    "/search",
    response_model=SuccessEnvelope[FestivalPinSearchResult],
    summary="1단계: TourAPI 수집 → 원문 JSONL 저장",
    description=(
        "TourAPI 조회 후 rag/output/festival_documents.jsonl에 저장합니다. "
    ),
)
async def search_festivals_from_tourapi(
    service: FestivalPinServiceDep,
    start_date: str = Query(..., min_length=8, max_length=8, description="YYYYMMDD"),
    end_date: str = Query(..., min_length=8, max_length=8, description="YYYYMMDD"),
    limit: int = Query(default=10, ge=1, le=50, description="최대 수집 건수"),
) -> SuccessEnvelope[FestivalPinSearchResult]:
    try:
        parsed_start = validate_yyyymmdd(start_date, label="start_date")
        parsed_end = validate_yyyymmdd(end_date, label="end_date")
    except ValueError as exc:
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail=str(exc),
        ) from exc
    if parsed_start > parsed_end:
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail="start_date는 end_date보다 이후일 수 없습니다.",
        )

    try:
        body = await service.search_and_save(
            start_date=parsed_start,
            end_date=parsed_end,
            limit=limit,
        )
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.OK)


@router.post(
    "/transform",
    response_model=SuccessEnvelope[FestivalPinTransformResult],
    summary="2단계: 원문 JSONL → AI 가공 → DB용 JSONL 저장",
    description=(
        "festival_documents.jsonl을 읽어 Gemini로 본문 가공 후 "
        "festival_pins_for_db.jsonl에 저장합니다. "
    ),
)
async def transform_festival_documents(
    service: FestivalPinServiceDep,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="가공 최대 건수 (미지정 시 원문 파일 전체)",
    ),
) -> SuccessEnvelope[FestivalPinTransformResult]:
    try:
        body = await service.transform_and_save(limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=ErrorCode.NOT_FOUND.http_status,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    return success_response(result=body, success_code=SuccessCode.CREATED)


@router.get(
    "/handoff",
    response_model=SuccessEnvelope[FestivalPinHandoffResult],
    summary="3단계: DB용 JSONL 조회",
    description=(
        "festival_pins_for_db.jsonl 가공본을 JSON으로 확인합니다. "
    ),
)
async def list_festival_handoff(
    service: FestivalPinServiceDep,
    start_date: str | None = Query(
        default=None,
        min_length=8,
        max_length=8,
        description="행사일 필터 시작 (end_date와 함께, 비우면 전체)",
    ),
    end_date: str | None = Query(
        default=None,
        min_length=8,
        max_length=8,
        description="행사일 필터 종료",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description="반환 최대 건수",
    ),
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
            raise HTTPException(
                status_code=ErrorCode.BAD_REQUEST.http_status,
                detail=str(exc),
            ) from exc
        if parsed_start > parsed_end:
            raise HTTPException(
                status_code=ErrorCode.BAD_REQUEST.http_status,
                detail="start_date는 end_date보다 이후일 수 없습니다.",
            )

    try:
        body = service.load_from_jsonl(
            start_date=parsed_start,
            end_date=parsed_end,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=ErrorCode.NOT_FOUND.http_status,
            detail=str(exc),
        ) from exc
    return success_response(result=body, success_code=SuccessCode.OK)
