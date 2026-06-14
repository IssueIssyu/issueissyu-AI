from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ContestDocumentDTO(BaseModel):
    """Linkareer 크롤 원문 1건 (contest_documents.jsonl)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "contentid": "319419",
                "pin_title": "[농심] 농심 메밀소바 짧은 글 공모전",
                "pin_content_raw": "■ 공모 주제\n- 여름 또는 메밀\n...",
                "source_url": "https://linkareer.com/activity/319419",
                "image_urls": [
                    "https://api.linkareer.com/attachments/828465",
                ],
                "event_start_time": "20260501",
                "event_end_time": "20260630",
                "host_org": "농심",
                "crawled_at": "2026-05-29T10:55:22",
            }
        }
    )

    contentid: str = Field(description="Linkareer activity ID")
    pin_title: str
    pin_content_raw: str = Field(description="상세 본문 원문")
    source_url: str = Field(description="원문 URL")
    image_urls: list[str] = Field(default_factory=list)
    event_start_time: str | None = Field(default=None, description="YYYYMMDD")
    event_end_time: str | None = Field(default=None, description="YYYYMMDD")
    host_org: str = ""
    crawled_at: str | None = None


class ContestDocumentsListResult(BaseModel):
    """contest_documents.jsonl 조회 결과."""

    filter_start_date: str | None = Field(
        default=None,
        description="접수/행사 기간 필터 시작 YYYYMMDD",
    )
    filter_end_date: str | None = Field(
        default=None,
        description="접수/행사 기간 필터 종료 YYYYMMDD",
    )
    saved_documents_path: str
    total_in_file: int
    matched_count: int
    count: int
    documents: list[ContestDocumentDTO]
    hint: str | None = None


class ContestCrawlResult(BaseModel):
    """POST /contest-pins/crawl 실행 결과."""

    saved_documents_path: str
    new_count: int
    skipped_expired: int
    skipped_duplicate: int
    errors: int
    total_count: int
    start_page: int = Field(default=1, description="크롤 시작 목록 페이지")
    max_pages: int = Field(default=1, description="시작 페이지부터 순회한 페이지 수")
    hint: str | None = None


class ContestPinHandoffDTO(BaseModel):
    """DB 전달용 contest_pins_for_db.jsonl 1행."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "contentid": "319419",
                "title": "[농심] 농심 메밀소바 짧은 글 공모전",
                "pin_content": "여름 메밀소바 주제로...\n\n#공모전 #대외활동",
                "cardnews_image_urls": [
                    "rag/output/contest_cardnews/319419/slide_01.png",
                    "rag/output/contest_cardnews/319419/slide_02.png",
                ],
                "source_url": "https://linkareer.com/activity/319419",
            },
        },
    )

    contentid: str
    title: str = Field(description="pin.pin_title")
    pin_content: str = Field(description="인스타 캡션 또는 정리 본문 + 원문 링크")
    cardnews_image_urls: list[str] = Field(
        default_factory=list,
        description="템플릿 카드뉴스 슬라이드 경로 → pin_image",
    )
    source_url: str = Field(default="", description="Linkareer 원문 URL")

    @classmethod
    def from_row(cls, row: dict) -> ContestPinHandoffDTO:
        data = dict(row) if isinstance(row, dict) else {}
        if not str(data.get("title") or "").strip():
            legacy = str(data.get("pin_title") or "").strip()
            if legacy:
                data["title"] = legacy
        return cls.model_validate(data)


class ContestPinTransformResult(BaseModel):
    input_path: str
    output_path: str
    processed_count: int
    error_count: int
    errors: list[dict] = Field(default_factory=list)
    pins: list[ContestPinHandoffDTO] = Field(default_factory=list)
    hint: str | None = None
    skipped_duplicate_count: int = 0
    skipped_expired_count: int = 0
    pending_count: int = 0
    remaining_pending_count: int = Field(
        default=0,
        description="가공 후에도 handoff·DB에 없는 원문 건수",
    )


class ContestPinHandoffResult(BaseModel):
    output_path: str
    total_in_file: int
    count: int
    pins: list[ContestPinHandoffDTO] = Field(default_factory=list)
    hint: str | None = None
