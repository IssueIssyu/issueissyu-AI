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
    retrieval_score: float | None = None  # 1차 벡터·하이브리드 검색
    rerank_score: float | None = None  # 2차 rerank (LLM에 넣을 문맥 선별, 정렬 기준)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ComplaintEmailLlmBundle(BaseModel):
    # 의견서 HTML 생성 LLM에 넘기는 JSON
    pin_title: str
    pin_content: str
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
    # 청원 최종 산출물
    opinion_html: str
    opinion_pdf_bytes: bytes
    notification_email_body: str
    reliability_score: float = Field(ge=0.0, le=1.0)
