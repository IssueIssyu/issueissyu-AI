from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FestivalPinDTO(BaseModel):
    # DB INSERT용 축제 핀 스키마 (pin / event_pin / pin_image 매핑)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "contentid": "2986679",
                "pin_type": "FESTIVAL",
                "pin_title": "가족의 달 어린이 축제",
                "pin_content_raw": "공식 행사 소개 원문...",
                "pin_content": "요즘 주말에 어디 갈지 고민된다면...\n\n#지역축제 #축제추천",
                "longitude": "126.565811815577",
                "latitude": "37.4817529989573",
                "image_urls": [
                    "https://tong.visitkorea.or.kr/cms/resource/84/4061184_image2_1.jpg",
                ],
                "event_start_time": "20260505",
                "event_end_time": "20260505",
                "addr": "인천광역시 중구 ...",
                "tel": "032-000-0000",
            }
        }
    )

    contentid: str = Field(description="TourAPI contentid (재수집, 중복 방지)")
    pin_type: str = Field(default="FESTIVAL", description="pin.pin_type")
    pin_title: str = Field(description="pin.pin_title")
    pin_content_raw: str = Field(description="TourAPI 공식 소개 원문 (보관용)")
    pin_content: str = Field(
        description="AI 가공 본문 → pin.pin_content (반려동물·숙박은 transform 시 본문에 포함)",
    )
    longitude: str | None = Field(default=None, description="경도 → pin_location(백엔드)")
    latitude: str | None = Field(default=None, description="위도 → pin_location(백엔드)")
    image_urls: list[str] = Field(
        default_factory=list,
        description="이미지 URL 목록 → pin_image",
    )
    event_start_time: str | None = Field(
        default=None,
        description="행사 시작일 YYYYMMDD → event_pin.event_start_time",
    )
    event_end_time: str | None = Field(
        default=None,
        description="행사 종료일 YYYYMMDD → event_pin.event_end_time",
    )
    addr: str | None = Field(default=None, description="주소 (pin_location.detail_address 등)")
    tel: str | None = Field(default=None, description="연락처")


class FestivalPinSourceDTO(BaseModel):
    # TourAPI 실시간 수집 1건 (transform 전 원문)
    contentid: str
    pin_title: str
    pin_content: str = Field(description="TourAPI 공식 소개 원문")
    addr: str = ""
    longitude: str | None = None
    latitude: str | None = None
    event_start_time: str | None = None
    event_end_time: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    tel: str = ""
    pet_friendly: str = "정보 없음"
    stay_available: str = "정보 없음"


class FestivalPinSearchResult(BaseModel):
    # TourAPI 수집 + 원문 JSONL 저장 결과
    query_start_date: str
    query_end_date: str
    count: int
    saved_documents_path: str = Field(
        description="저장된 원문 JSONL (festival_documents.jsonl)",
    )
    pins: list[FestivalPinSourceDTO]
    stats: dict[str, int] = Field(
        default_factory=dict,
        description="수집 통계 (documents, detail_errors 등)",
    )
    hint: str | None = Field(default=None, description="다음 단계 안내")


class FestivalPinTransformResult(BaseModel):
    # Gemini 가공 + DB 핸드오프 JSONL 저장 결과

    input_path: str
    output_path: str
    processed_count: int
    error_count: int
    errors: list[dict] = Field(default_factory=list)
    pins: list[FestivalPinDTO] = Field(description="가공된 축제 핀 (DB INSERT 스키마)")
    hint: str | None = None


class FestivalPinHandoffResult(BaseModel):
    # Swagger 응답: pins 배열에 축제 핀 전체 필드가 펼쳐짐

    filter_start_date: str | None = Field(
        default=None,
        description="조회 기간 시작 YYYYMMDD (미지정 시 기간 필터 없음)",
    )
    filter_end_date: str | None = Field(
        default=None,
        description="조회 기간 종료 YYYYMMDD",
    )
    total_in_file: int = Field(description="JSONL 전체 행 수")
    matched_count: int = Field(description="기간 필터 적용 후 건수 (limit 적용 전)")
    count: int = Field(description="pins 길이 (limit 적용 후)")
    pins: list[FestivalPinDTO] = Field(description="축제 핀 목록 (DB INSERT 스키마)")
    hint: str | None = Field(
        default=None,
        description="조회 건수가 적을 때 원인 안내",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filter_start_date": "20260501",
                "filter_end_date": "20260531",
                "total_in_file": 12,
                "matched_count": 3,
                "count": 3,
                "hint": None,
                "pins": [
                    {
                        "contentid": "2986679",
                        "pin_type": "FESTIVAL",
                        "pin_title": "가족의 달 어린이 축제",
                        "pin_content_raw": "공식 소개 원문...",
                        "pin_content": "요즘 주말에 어디 갈지...",
                        "longitude": "126.56",
                        "latitude": "37.48",
                        "image_urls": [],
                        "event_start_time": "20260505",
                        "event_end_time": "20260510",
                        "addr": "인천광역시 중구",
                        "tel": "",
                    },
                    {
                        "contentid": "3012345",
                        "pin_type": "FESTIVAL",
                        "pin_title": "봄꽃 축제",
                        "pin_content_raw": "...",
                        "pin_content": "...",
                        "longitude": "127.0",
                        "latitude": "37.5",
                        "image_urls": [],
                        "event_start_time": "20260515",
                        "event_end_time": "20260520",
                        "addr": "경기도 ...",
                        "tel": "",
                    },
                ],
            }
        }
    )

