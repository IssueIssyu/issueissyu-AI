from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

class ComplaintEmailVlmImageSlot(BaseModel):
    # 프롬프트용 이미지 메타
    index: int = Field(ge=1)
    filename: str
    photo_address: str | None = None


class ComplaintEmailVlmInput(BaseModel):
    # 이슈 핀 제목, 본문 + 이미지 메타
    pin_title: str
    pin_content: str
    photo_address: str | None = None
    image_slots: list[ComplaintEmailVlmImageSlot] = Field(default_factory=list)


class ComplaintEmailVlmOutput(BaseModel):
    # 청원 분석 VLM 결과
    type: str
    domain: str
    subcategory: str | None = None
    summary: str = ""
    objects: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    query: str = ""

    model_config = ConfigDict(from_attributes=True)

class ComplaintEmailRagHit(BaseModel):
    text: str = ""
    retrieval_score: float | None = None  # 1차 벡터, 하이브리드 검색
    rerank_score: float | None = None  # 2차 rerank (LLM에 넣을 문맥 선별, 정렬 기준)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ComplaintEmailRagPipelineResult(BaseModel):
    rag_query: str = ""
    retrieval_hits: list[ComplaintEmailRagHit] = Field(default_factory=list)
    reranked_hits: list[ComplaintEmailRagHit] = Field(default_factory=list)


class ComplaintEmailRagRunResult(BaseModel):
    # VLM + RAG 파이프라인까지만 실행한 결과

    pin_title: str = ""
    pin_content: str = ""
    photo_address: str | None = None
    image_count: int = 0
    vlm_input: ComplaintEmailVlmInput
    vlm_output: ComplaintEmailVlmOutput
    rag: ComplaintEmailRagPipelineResult
    department: str | None = None


class ComplaintEmailLlmBundle(BaseModel):
    # 의견서 HTML 생성 LLM에 넘기는 JSON
    pin_title: str
    pin_content: str
    rag_query: str = ""
    vlm: ComplaintEmailVlmOutput
    rag_hits: list[ComplaintEmailRagHit] = Field(default_factory=list)


class ComplaintEmailValidationResult(BaseModel):
    # 핀 검증 VLM 기반 신뢰도
    reliability_score: float = Field(ge=0.0, le=1.0)
    validity: bool
    error_code: str | None = None
    scene_summary: str | None = None
    risk_note: str | None = None


class ComplaintEmailGenerateResult(BaseModel):
    # 입력
    pin_title: str = ""
    pin_content: str = ""
    photo_address: str | None = None
    image_count: int = 0
    department: str | None = None
    # 파이프라인 중간 산출
    vlm_input: ComplaintEmailVlmInput | None = None
    vlm_output: ComplaintEmailVlmOutput | None = None
    rag: ComplaintEmailRagPipelineResult | None = None
    llm_bundle: ComplaintEmailLlmBundle | None = None
    validation: ComplaintEmailValidationResult | None = None
    # 최종 산출물
    opinion_html: str = ""
    opinion_pdf_bytes: bytes = b""
    notification_email_subject: str = ""
    notification_email_body: str = ""
    reliability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reliability_basis: str = ""


class ComplaintEmailPinInputApi(BaseModel):
    pin_title: str
    pin_content: str
    photo_address: str | None = None
    image_count: int = 0


class ComplaintEmailOutputsApi(BaseModel):
    opinion_html: str
    opinion_pdf_base64: str
    notification_email_subject: str
    notification_email_body: str
    reliability_score: float = Field(ge=0.0, le=1.0)
    department: str | None = None
    reliability_basis: str = ""


class ComplaintEmailRagPipelineApi(BaseModel):
    # RAG 1차 검색, 2차 rerank를 분리해 표시
    rag_query: str = ""
    retrieval: list[ComplaintEmailRagHit] = Field(
        default_factory=list,
        description="1차 벡터, 하이브리드 검색 결과 (retrieval_score)",
    )
    rerank: list[ComplaintEmailRagHit] = Field(
        default_factory=list,
        description="2차 rerank 결과 (rerank_score, LLM 입력 문맥)",
    )


class ComplaintEmailRagApiResponse(BaseModel):
    # RAG, rerank 디버그 전용 응답
    input: ComplaintEmailPinInputApi
    vlm_input: ComplaintEmailVlmInput
    vlm_output: ComplaintEmailVlmOutput
    rag: ComplaintEmailRagPipelineApi
    department: str | None = None


class ComplaintEmailOutputsOnlyApiResponse(BaseModel):
    # BE 연동용 — 최종 산출물만
    input: ComplaintEmailPinInputApi
    outputs: ComplaintEmailOutputsApi

    @classmethod
    def from_generate_result(cls, result: ComplaintEmailGenerateResult) -> ComplaintEmailOutputsOnlyApiResponse:
        import base64

        return cls(
            input=ComplaintEmailPinInputApi(
                pin_title=result.pin_title,
                pin_content=result.pin_content,
                photo_address=result.photo_address,
                image_count=result.image_count,
            ),
            outputs=ComplaintEmailOutputsApi(
                opinion_html=result.opinion_html,
                opinion_pdf_base64=base64.b64encode(result.opinion_pdf_bytes).decode("ascii"),
                notification_email_subject=result.notification_email_subject,
                notification_email_body=result.notification_email_body,
                reliability_score=result.reliability_score,
                department=result.department,
                reliability_basis=result.reliability_basis,
            ),
        )


def build_rag_api_response(result: ComplaintEmailRagRunResult) -> ComplaintEmailRagApiResponse:
    return ComplaintEmailRagApiResponse(
        input=ComplaintEmailPinInputApi(
            pin_title=result.pin_title,
            pin_content=result.pin_content,
            photo_address=result.photo_address,
            image_count=result.image_count,
        ),
        vlm_input=result.vlm_input,
        vlm_output=result.vlm_output,
        rag=ComplaintEmailRagPipelineApi(
            rag_query=result.rag.rag_query,
            retrieval=result.rag.retrieval_hits,
            rerank=result.rag.reranked_hits,
        ),
        department=result.department,
    )


class ComplaintPetitionApplyResponse(BaseModel):
    petition_id: int
    issue_pin_id: int
    location_department_id: int
    location_id: int
    department_name: str
    location_department_email: str
    generated_on: str
    pdf_s3_key: str
    pdf_s3_url: str
    email_subject: str
    email_body: str
    reliability_score: float = Field(ge=0.0, le=1.0)
    reliability_basis: str
    status: str


class ComplaintPetitionBulkSendRequest(BaseModel):
    petition_ids: list[int] = Field(default_factory=list)


class ComplaintPetitionBulkSendItem(BaseModel):
    petition_id: int
    status: str
    issue_pin_id: int
    location_department_id: int
    location_department_email: str
    reason: str | None = None


class ComplaintPetitionBulkSendResponse(BaseModel):
    sent_count: int = 0
    failed_count: int = 0
    items: list[ComplaintPetitionBulkSendItem] = Field(default_factory=list)
