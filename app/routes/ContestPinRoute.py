from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from app.core.codes import ErrorCode, SuccessCode
from app.core.deps import ContestEventIngestServiceDep, ContestPinServiceDep, S3UtilDep
from app.core.responses import SuccessEnvelope, success_response
from app.schemas.ContestPinDTO import (
    ContestCrawlResult,
    ContestDocumentsListResult,
    ContestPinHandoffResult,
    ContestPinTransformResult,
)
from app.utils.festival_date_filter import validate_yyyymmdd

router = APIRouter(prefix="/contest-pins", tags=["contest-pins"])


@router.post(
    "/crawl",
    response_model=SuccessEnvelope[ContestCrawlResult],
    summary="1단계: Linkareer 크롤링 → contest_documents.jsonl 저장",
    description=(
        "Playwright로 Linkareer 공모전 목록·상세를 수집해 "
        "rag/output/contest_documents.jsonl에 저장합니다. "
        "서버에 Chromium(playwright install chromium)이 필요하며 요청이 수 분 걸릴 수 있습니다."
    ),
)
async def crawl_contests_from_linkareer(
    service: ContestPinServiceDep,
    start_page: int = Query(default=1, ge=1, le=50, description="목록 시작 페이지 번호"),
    max_pages: int = Query(default=1, ge=1, le=50, description="시작 페이지부터 순회할 페이지 수"),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=100,
        description="상세 수집 최대 건수 (미지정 시 목록에서 찾은 신규 전체)",
    ),
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
        msg = str(exc)
        status = (
            503
            if "playwright" in msg.lower()
            else ErrorCode.INTERNAL_SERVER_ERROR.http_status
        )
        raise HTTPException(status_code=status, detail=msg) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=ErrorCode.INTERNAL_SERVER_ERROR.http_status,
            detail=str(exc) or repr(exc),
        ) from exc

    code = SuccessCode.CREATED if body.new_count else SuccessCode.OK
    return success_response(result=body, success_code=code)


@router.get(
    "/documents",
    response_model=SuccessEnvelope[ContestDocumentsListResult],
    summary="크롤 원문 JSONL 조회 (Swagger 확인용)",
    description="contest_documents.jsonl 내용을 JSON으로 반환합니다.",
)
async def list_contest_documents(
    service: ContestPinServiceDep,
    contentid: str | None = Query(
        default=None,
        description="특정 activity ID만 조회",
    ),
    start_date: str | None = Query(
        default=None,
        min_length=8,
        max_length=8,
        description="기간 필터 시작 YYYYMMDD (end_date와 함께)",
    ),
    end_date: str | None = Query(
        default=None,
        min_length=8,
        max_length=8,
        description="기간 필터 종료 YYYYMMDD",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description="반환 최대 건수",
    ),
) -> SuccessEnvelope[ContestDocumentsListResult]:
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
        body = service.load_documents_from_jsonl(
            start_date=parsed_start,
            end_date=parsed_end,
            limit=limit,
            contentid=contentid,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=ErrorCode.NOT_FOUND.http_status,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST.http_status,
            detail=str(exc),
        ) from exc

    return success_response(result=body, success_code=SuccessCode.OK)


def _runtime_error_response(exc: RuntimeError) -> HTTPException:
    return HTTPException(
        status_code=ErrorCode.INTERNAL_SERVER_ERROR.http_status,
        detail=str(exc),
    )


@router.post(
    "/cardnews",
    response_model=SuccessEnvelope[ContestPinTransformResult],
    summary="2단계: 원문 → 텍스트 카드뉴스 PNG + DB용 JSONL",
    description=(
        "contest_documents.jsonl의 pin_content_raw로 Gemini 슬라이드 문구를 만들고, "
        "브라우저형 파스텔 템플릿·저장된 캐릭터 PNG로 slide_XX.png를 렌더합니다. "
        "크롤한 공고 이미지는 사용하지 않습니다."
    ),
)
async def generate_contest_cardnews(
    service: ContestPinServiceDep,
    ingest_service: ContestEventIngestServiceDep,
    s3_util: S3UtilDep,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=20,
        description="가공 최대 건수 (미지정 시 원문 파일 전체, 최대 20 권장)",
    ),
    contentid: str | None = Query(
        default=None,
        description="특정 activity ID만 카드뉴스 생성",
    ),
    with_caption: bool = Query(
        default=True,
        description="인스타용 캡션을 pin_content에 사용",
    ),
    skip_db_duplicates: bool = Query(
        default=True,
        description="DB에 이미 있는 contest_api_id는 LLM 가공 스킵",
    ),
) -> SuccessEnvelope[ContestPinTransformResult]:
    try:
        db_ids: set[int] | None = None
        if skip_db_duplicates:
            db_ids = await ingest_service.get_imported_contest_api_ids()
        body = await service.cardnews_and_save(
            limit=limit,
            with_caption=with_caption,
            contentid=contentid,
            s3_util=s3_util,
            db_contest_api_ids=db_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=ErrorCode.NOT_FOUND.http_status,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise _runtime_error_response(exc) from exc

    code = SuccessCode.CREATED if body.processed_count else SuccessCode.OK
    return success_response(result=body, success_code=code)


@router.get(
    "/handoff",
    response_model=SuccessEnvelope[ContestPinHandoffResult],
    summary="DB용 JSONL 조회 (카드뉴스 핸드오프)",
    description="contest_pins_for_db.jsonl을 조회합니다.",
)
async def list_contest_handoff(
    service: ContestPinServiceDep,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description="반환 최대 건수",
    ),
) -> SuccessEnvelope[ContestPinHandoffResult]:
    try:
        body = service.load_handoff_from_jsonl(limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=ErrorCode.NOT_FOUND.http_status,
            detail=str(exc),
        ) from exc
    return success_response(result=body, success_code=SuccessCode.OK)
