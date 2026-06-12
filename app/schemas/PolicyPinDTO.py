from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PolicyPinSourceDTO(BaseModel):
    # 정책뉴스 API 수집 1건 (transform 전 원문)

    contentid: str = Field(description="NewsItemId")
    pin_title: str
    pin_content: str = Field(description="본문 (HTML 제거 또는 TEXT)")
    pin_content_raw: str = Field(description="DataContents 원문")
    minister: str = ""
    grouping_code: str = ""
    contents_type: str = "H"
    approve_date: str = ""
    event_start_time: str | None = Field(
        default=None,
        description="승인일 YYYYMMDD → event_pin.event_start_time",
    )
    event_end_time: str | None = Field(
        default=None,
        description="승인일 YYYYMMDD → event_pin.event_end_time",
    )
    original_image_urls: list[str] = Field(
        default_factory=list,
        description="원본 대표 이미지 (OriginalimgUrl 등) → pin_image is_main",
    )
    cardnews_image_urls: list[str] = Field(
        default_factory=list,
        description="카드뉴스 슬라이드/API 인라인 이미지 → pin_image",
    )
    image_urls: list[str] = Field(
        default_factory=list,
        description="original + cardnews 통합 (하위 호환)",
    )
    source_url: str = ""
    subtitles: str = ""
    contents_status: str = ""


class PolicyPinHandoffDTO(BaseModel):
    # DB 전달용 policy_pins_for_db.jsonl 1행 스키마

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "올 하반기부터 개인정보 침해 위험 실태 점검",
                "pin_content": "개인정보, 이제 위험도에 따라...\n\n#정책 #개인정보보호",
                "cardnews_image_urls": [
                    "rag/output/policy_cardnews/148965005/slide_01.png",
                    "rag/output/policy_cardnews/148965005/slide_02.png",
                ],
                "source_url": "https://www.korea.kr/news/policyNewsView.do?newsId=148965005",
            },
        },
    )

    title: str = Field(description="pin.pin_title")
    pin_content: str = Field(description="AI 가공 본문 → pin.pin_content")
    cardnews_image_urls: list[str] = Field(
        default_factory=list,
        description="카드뉴스 슬라이드 경로/URL → pin_image",
    )
    source_url: str = Field(default="", description="기사 원문 URL")

    @classmethod
    def from_row(cls, row: dict) -> PolicyPinHandoffDTO:
        data = dict(row) if isinstance(row, dict) else {}
        if not str(data.get("title") or "").strip():
            legacy = str(data.get("pin_title") or "").strip()
            if legacy:
                data["title"] = legacy
        return cls.model_validate(data)


# 하위 호환 별칭
PolicyPinDTO = PolicyPinHandoffDTO


class PolicyPinTransformResult(BaseModel):
    input_path: str
    output_path: str = Field(description="DB용 JSONL 경로 (pins와 동일 내용)")
    processed_count: int
    error_count: int
    errors: list[dict] = Field(default_factory=list)
    pins: list[PolicyPinHandoffDTO] = Field(
        description="output_path JSONL에 저장된 행과 동일 (DB 전달 4필드)",
    )
    hint: str | None = None
    skipped_duplicate_count: int = 0
    pending_count: int = 0


class PolicyPinHandoffResult(BaseModel):
    output_path: str = Field(description="policy_pins_for_db.jsonl (transform과 동일 파일)")
    total_in_file: int = Field(description="JSONL 전체 행 수")
    count: int = Field(description="반환 건수 (limit 적용 후)")
    pins: list[PolicyPinHandoffDTO] = Field(
        description="JSONL 내용 (transform 응답 pins와 동일, limit만 다를 수 있음)",
    )
    hint: str | None = Field(default=None, description="조회 안내")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "output_path": "rag/output/policy_pins_for_db.jsonl",
                "total_in_file": 5,
                "count": 5,
                "hint": None,
                "pins": [
                    {
                        "title": "올 하반기부터 개인정보 침해 위험 실태 점검",
                        "pin_content": "개인정보, 이제 위험도에 따라...",
                        "cardnews_image_urls": [
                            "rag/output/policy_cardnews/148965005/slide_01.png",
                        ],
                        "source_url": "https://www.korea.kr/news/policyNewsView.do?newsId=148965005",
                    },
                ],
            },
        },
    )


class PolicyPinSearchResult(BaseModel):
    query_start_date: str
    query_end_date: str
    count: int
    saved_documents_path: str
    pins: list[PolicyPinSourceDTO]
    stats: dict[str, int] = Field(default_factory=dict)
    hint: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query_start_date": "20260522",
                "query_end_date": "20260524",
                "count": 2,
                "saved_documents_path": "rag/output/policy_documents.jsonl",
                "stats": {"documents": 2, "chunks": 1, "api_errors": 0},
                "hint": "다음: POST /policy-pins/transform",
                "pins": [
                    {
                        "contentid": "148965005",
                        "pin_title": "정책 뉴스 제목",
                        "pin_content": "본문 요약 텍스트...",
                        "pin_content_raw": "<p>...</p>",
                        "minister": "개인정보보호위원회",
                        "approve_date": "05/22/2026 17:32:00",
                        "event_start_time": "20260522",
                        "event_end_time": "20260522",
                        "image_urls": [
                            "https://www.korea.kr/newsWeb/resources/attaches/2026.05/22/example.jpg",
                        ],
                        "source_url": "https://www.korea.kr/news/policyNewsView.do?newsId=148965005",
                    },
                ],
            },
        },
    )
