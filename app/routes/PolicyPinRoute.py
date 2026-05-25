from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.codes import ErrorCode, SuccessCode
from app.core.deps import PolicyPinServiceDep
from app.core.responses import SuccessEnvelope, success_response
from app.schemas.PolicyPinDTO import (
    PolicyPinHandoffResult,
    PolicyPinSearchResult,
    PolicyPinTransformResult,
)
from app.utils.policy_news_parse import validate_yyyymmdd

router = APIRouter(prefix="/policy-pins", tags=["policy-pins"])


def _runtime_error_response(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if "GEMINI" in detail or "POLICY" in detail:
        status = ErrorCode.VLM_NOT_CONFIGURED.http_status
    else:
        status = ErrorCode.INTERNAL_SERVER_ERROR.http_status
    return HTTPException(status_code=status, detail=detail)


@router.get(
    "/search",
    response_model=SuccessEnvelope[PolicyPinSearchResult],
    summary="정책뉴스 OpenAPI 수집 → 원문 JSONL 저장",
    description=(
        "정책뉴스 API를 승인일(start_date~end_date) 기준으로 조회해 "
        "policy_documents.jsonl에 저장합니다. 기간 필터는 이 단계에서만 적용됩니다."
    ),
)
async def search_policy_news(
    service: PolicyPinServiceDep,
    start_date: str = Query(..., min_length=8, max_length=8, description="YYYYMMDD"),
    end_date: str = Query(..., min_length=8, max_length=8, description="YYYYMMDD"),
    limit: int = Query(default=10, ge=1, le=50, description="최대 수집 건수"),
) -> SuccessEnvelope[PolicyPinSearchResult]:
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
    response_model=SuccessEnvelope[PolicyPinTransformResult],
    summary="원문 JSONL → AI 가공 → DB용 JSONL 저장",
    description=(
        "search로 저장된 policy_documents.jsonl을 가공해 "
        "policy_pins_for_db.jsonl을 만듭니다."
    ),
)
async def transform_policy_documents(
    service: PolicyPinServiceDep,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="가공 최대 건수 (미지정 시 원문 파일 전체)",
    ),
) -> SuccessEnvelope[PolicyPinTransformResult]:
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
    response_model=SuccessEnvelope[PolicyPinHandoffResult],
    summary="DB용 JSONL 조회",
    description=(
        "policy_pins_for_db.jsonl을 조회합니다. "
        "기간 필터는 GET /search에서 이미 반영된 뒤 transform으로 4필드만 추출된 결과입니다."
    ),
)
async def list_policy_handoff(
    service: PolicyPinServiceDep,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description="반환 최대 건수",
    ),
) -> SuccessEnvelope[PolicyPinHandoffResult]:
    try:
        body = service.load_from_jsonl(limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=ErrorCode.NOT_FOUND.http_status,
            detail=str(exc),
        ) from exc
    return success_response(result=body, success_code=SuccessCode.OK)
