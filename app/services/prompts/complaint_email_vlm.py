from __future__ import annotations

from app.schemas.ComplaintEmailDTO import ComplaintEmailVlmImageSlot, ComplaintEmailVlmInput


class ComplaintEmailVlmCatalog:
    # 청원 분석 VLM
    CATEGORY_TYPES: tuple[str, ...] = (
        "불법주정차",
        "불법쓰레기투기",
        "시설물 민원",
        "기타/판단불가",
    )

    ADMIN_DOMAINS: tuple[str, ...] = (
        "건축허가",
        "경제",
        "공통",
        "교통",
        "농업_축산",
        "문화_체육_관광",
        "보건소",
        "복지",
        "산림",
        "상하수도",
        "세무",
        "안전건설",
        "위생",
        "자동차",
        "정보통신",
        "토지",
        "행정",
        "환경미화",
    )

    DEFAULT_TYPE = "기타/판단불가"
    DEFAULT_DOMAIN = "공통"
    DEFAULT_SUBCATEGORY = "판단불가"
    KEYWORDS_MAX = 8

    TYPE_DOMAIN_FALLBACK: dict[str, str] = {
        "불법주정차": "교통",
        "불법쓰레기투기": "환경미화",
        "시설물 민원": "안전건설",
        "기타/판단불가": DEFAULT_DOMAIN,
    }

    TYPE_PLAUSIBLE_DOMAINS: dict[str, frozenset[str]] = {
        "불법주정차": frozenset({"교통", "자동차", DEFAULT_DOMAIN, "행정"}),
        "불법쓰레기투기": frozenset({"환경미화", "위생", DEFAULT_DOMAIN, "행정"}),
        "시설물 민원": frozenset(
            {
                "안전건설",
                "상하수도",
                "산림",
                "문화_체육_관광",
                "복지",
                "정보통신",
                "건축허가",
                "토지",
                "위생",
                DEFAULT_DOMAIN,
                "행정",
            },
        ),
    }

    @classmethod
    def format_allowed(cls, values: tuple[str, ...]) -> str:
        return ", ".join(values)

    @classmethod
    def response_json_schema(cls) -> dict:
        return {
            "type": "object",
            "required": [
                "type",
                "domain",
                "subcategory",
                "summary",
                "objects",
                "keywords",
                "query",
            ],
            "properties": {
                "type": {"type": "string", "enum": list(cls.CATEGORY_TYPES)},
                "domain": {"type": "string", "enum": list(cls.ADMIN_DOMAINS)},
                "subcategory": {"type": "string", "nullable": true},
                "subcategory": {"type": "string", "nullable": True},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "query": {"type": "string"},
            },
        }


class ComplaintEmailVlmPromptBuilder:
    # 청원용 분석 VLM 프롬프트 (검증, error_code 없음)

    def __init__(self, catalog: type[ComplaintEmailVlmCatalog] = ComplaintEmailVlmCatalog) -> None:
        self._catalog = catalog

    def build_from_input(self, request: ComplaintEmailVlmInput) -> str:
        cat = self._catalog
        photo_address_text = self._render_optional(request.photo_address)
        pin_title = request.pin_title.strip()
        pin_content = request.pin_content.strip()
        types_line = cat.format_allowed(cat.CATEGORY_TYPES)
        domains_line = cat.format_allowed(cat.ADMIN_DOMAINS)
        image_slots_text = self._format_image_slots(request.image_slots)
        image_count = len(request.image_slots) or 1

        return f"""
            [청원 의견서 작성용 이미지·텍스트 분석 — VLM]
            
            [역할]
            지자체 청원(의견 제출) 문서 작성을 돕기 위해, 첨부된 {image_count}장의 이미지와 이슈 핀(제목·본문)을 분석한다.
            - type/domain 분류
            - summary, objects 추출 (이미지에서 확인된 내용만)
            - RAG 검색용 keywords, query 생성
            
            [원칙]
            입력에 없는 정보는 생성하지 않는다. 모르면 null 또는 "판단불가".
            감정·구어체 금지. 확인되지 않은 사실·위법 확정·고의성은 추측하지 않는다.
            번호판·얼굴 등 개인정보는 summary·objects에 그대로 쓰지 않는다.
            error_code·validity·위치 검증은 하지 않는다 (별도 단계).
            
            [이미지]
            첨부 순서와 동일:
            {image_slots_text}
            
            [이슈 핀]
            제목: {pin_title}
            본문: {pin_content}
            
            [사진 메타 주소(참고)]
            {photo_address_text}
            
            [분류]
            type: {types_line}
            domain: {domains_line}
            힌트: 주정차·도로→교통, 쓰레기·무단투기→환경미화, 시설 파손→안전건설, 불확실→공통
            
            [type 기준]
            불법주정차: 부적절 정차·주차 | 불법쓰레기투기: 쓰레기·폐기물 방치 | 시설물 민원: 시설 파손·고장 | 기타/판단불가: 분류 어려움
            
            [검색]
            keywords: 5~8개 명사, 일반어(문제, 민원, 사진) 금지.
            query: 1문장 30~50자. photo_address가 있으면 포함 가능.
            
            [출력 JSON]
            {{
              "type": "",
              "domain": "",
              "subcategory": "",
              "summary": "",
              "objects": [],
              "keywords": [],
              "query": ""
            }}
        """.strip()

    @staticmethod
    def _format_image_slots(slots: list[ComplaintEmailVlmImageSlot]) -> str:
        if not slots:
            return "(이미지 없음)"
        return "\n".join(
            f"[{s.index}] {s.filename} — 메타 주소: {s.photo_address or 'null'}"
            for s in slots
        )

    @staticmethod
    def _render_optional(value: str | None) -> str:
        if value is None:
            return "null"
        stripped = value.strip()
        return stripped if stripped else "null"
