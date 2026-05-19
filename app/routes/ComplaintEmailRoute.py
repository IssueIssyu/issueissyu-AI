from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from app.core.codes import ErrorCode, SuccessCode
from app.core.deps import ComplaintEmailServiceDep, CurrentUserIdDep
from app.core.exceptions import raise_business_exception
from app.core.responses import success_response
from app.schemas.ComplaintEmailDTO import (
    ComplaintEmailGenerateResult,
    ComplaintEmailOutputsOnlyApiResponse,
    build_rag_api_response,
)
from app.schemas.IssueDTO import ImageWithLocation

router = APIRouter(prefix="/complaint-email", tags=["complaint-email"])


def _build_image_rows(
    images: list[UploadFile],
    photo_address: str | None,
) -> list[ImageWithLocation]:
    addr = photo_address.strip() if photo_address else None
    return [ImageWithLocation(image=upload, address=addr) for upload in images]


def _pdf_response(generated: ComplaintEmailGenerateResult) -> Response:
    pdf_bytes = generated.opinion_pdf_bytes
    if not pdf_bytes:
        raise_business_exception(ErrorCode.INTERNAL_SERVER_ERROR, "생성된 PDF가 비어 있습니다.")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="opinion.pdf"'},
    )


@router.post(
    "/pipeline/rag",
    summary="VLM + RAG(1차 검색·2차 rerank)만 실행",
    description=(
        "의견서·PDF·메일은 생성하지 않습니다. "
        "Swagger에서 retrieval / rerank 결과만 확인할 때 사용하세요."
    ),
)
async def run_complaint_email_rag_pipeline(
    _uid: CurrentUserIdDep,
    complaint_email_service: ComplaintEmailServiceDep,
    pin_title: Annotated[str, Form(description="이슈 핀 제목")],
    pin_content: Annotated[str, Form(description="이슈 핀 본문")],
    images: Annotated[list[UploadFile], File(description="현장 사진 1장 이상")],
    photo_address: Annotated[str | None, Form(description="사진 메타 주소(선택)")] = None,
):
    image_rows = _build_image_rows(images, photo_address)
    rag_result = await complaint_email_service.run_rag_pipeline(
        pin_title=pin_title,
        pin_content=pin_content,
        images=image_rows,
        photo_address=photo_address.strip() if photo_address else None,
    )
    payload = build_rag_api_response(rag_result)
    return success_response(
        result=payload.model_dump(by_alias=True, exclude_none=False),
        success_code=SuccessCode.COMPLAINT_EMAIL_GENERATE_SUCCESS,
    )


@router.post(
    "/generate/outputs",
    summary="청원 패키지 최종 산출물만 (JSON)",
    description=(
        "전체 파이프라인을 실행하고 **input + outputs** 만 반환합니다. "
        "opinion_html, opinion_pdf_base64, notification_email_body, reliability_score 포함. "
        "RAG 디버그는 **POST /complaint-email/pipeline/rag** 를 사용하세요."
    ),
)
async def generate_complaint_email_outputs(
    _uid: CurrentUserIdDep,
    complaint_email_service: ComplaintEmailServiceDep,
    pin_title: Annotated[str, Form(description="이슈 핀 제목")],
    pin_content: Annotated[str, Form(description="이슈 핀 본문")],
    images: Annotated[list[UploadFile], File(description="현장 사진 1장 이상")],
    photo_address: Annotated[str | None, Form(description="사진 메타 주소(선택)")] = None,
):
    image_rows = _build_image_rows(images, photo_address)
    generated = await complaint_email_service.generate_petition_package(
        pin_title=pin_title,
        pin_content=pin_content,
        images=image_rows,
        photo_address=photo_address.strip() if photo_address else None,
    )
    payload = ComplaintEmailOutputsOnlyApiResponse.from_generate_result(generated)
    return success_response(
        result=payload.model_dump(by_alias=True, exclude_none=False),
        success_code=SuccessCode.COMPLAINT_EMAIL_GENERATE_SUCCESS,
    )


@router.post(
    "/generate/pdf",
    summary="청원 의견서 PDF만 생성",
    description=(
        "전체 파이프라인 실행 후 **application/pdf** 바이너리만 반환합니다. "
        "JSON이 아니라 PDF 파일이므로 Swagger 응답이 `%PDF-1.4` 로 보이는 것이 정상입니다."
    ),
    responses={
        200: {
            "description": "생성된 의견서 PDF",
            "content": {"application/pdf": {}},
        },
    },
)
async def generate_complaint_email_pdf(
    _uid: CurrentUserIdDep,
    complaint_email_service: ComplaintEmailServiceDep,
    pin_title: Annotated[str, Form(description="이슈 핀 제목")],
    pin_content: Annotated[str, Form(description="이슈 핀 본문")],
    images: Annotated[list[UploadFile], File(description="현장 사진 1장 이상")],
    photo_address: Annotated[str | None, Form(description="사진 메타 주소(선택)")] = None,
):
    image_rows = _build_image_rows(images, photo_address)
    generated = await complaint_email_service.generate_petition_package(
        pin_title=pin_title,
        pin_content=pin_content,
        images=image_rows,
        photo_address=photo_address.strip() if photo_address else None,
    )
    return _pdf_response(generated)
