from __future__ import annotations

from app.schemas.ComplaintEmailDTO import ComplaintEmailVlmInput


class VlmCatalog:
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
    DEFAULT_PRIVACY_NOTE = "해당 없음"
    PRIVACY_RISK_NOTE = "주의) 개인정보 포함 가능성 있음"
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

    ERROR_CODES: tuple[str, ...] = (
        "E001_IMAGE_ANALYSIS_FAILED",
        "E002_OBJECT_NOT_IDENTIFIED",
        "E003_IRRELEVANT_IMAGE",
        "E004_CATEGORY_UNCLEAR",
        "E005_LOW_IMAGE_QUALITY",
        "E006_UNVERIFIABLE_CLAIM",
        "E007_PRIVACY_RISK",
        "E008_LOCATION_MISMATCH",
    )

    @classmethod
    def format_allowed(cls, values: tuple[str, ...]) -> str:
        return ", ".join(values)

    """@classmethod
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
                "subcategory": {"type": "string"},
                "summary": {"type": "string"},
                "objects": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "query": {"type": "string"},
            },
        }"""


class VlmPromptBuilder:
    # VLM 프롬프트 문자열 생성.

    def __init__(self, catalog: type[VlmCatalog] = VlmCatalog) -> None:
        self._catalog = catalog

    def build(
        self,
        *,
        user_text: str,
        user_location: str | None,
        photo_address: str | None,
    ) -> str:
        return self.build_from_input(
            ComplaintEmailVlmInput(
                user_text=user_text,
                user_location=user_location,
                photo_address=photo_address,
            ),
        )

    def build_from_input(self, request: ComplaintEmailVlmInput) -> str:
        catalog = self._catalog
        user_location_text = self._render_optional(request.user_location)
        photo_address_text = self._render_optional(request.photo_address)
        safe_user_text = request.user_text.strip()
        types_line = catalog.format_allowed(catalog.CATEGORY_TYPES)
        domains_line = catalog.format_allowed(catalog.ADMIN_DOMAINS)

        return f"""
            [AI 민원 이미지 분석 및 RAG 검색 보조]
            
            [역할]
            지자체 민원의 이미지·텍스트를 분석한다.
            - type/domain 분류
            - summary, objects 추출
            - keywords, query 생성
            
            [원칙]
            입력에 없는 정보는 생성하지 않는다. 모르면 null 또는 "판단불가".
            감정·구어체 금지. 사진에서 확인되지 않은 사실·시점·고의성·위법 확정은 추측하지 않는다.
            번호판·얼굴 등 개인정보는 출력하지 않는다.
            
            [입력]
            사용자 민원 내용: {safe_user_text}
            사용자 위치 정보: {user_location_text}
            사진 메타 주소:
            {photo_address_text}
            
            [분류]
            type: {types_line}
            domain: {domains_line}
            힌트: 주정차·도로·횡단보도→교통, 쓰레기·무단투기→환경미화, 시설 파손·보도·맨홀→안전건설, 불확실→공통
            
            [type 기준]
            불법주정차: 도로·인도·횡단보도·버스정류장 등 부적절 정차·주차
            불법쓰레기투기: 지정 장소 외 쓰레기·폐기물·오물 방치
            시설물 민원: 공공시설·생활시설 파손·고장·훼손
            기타/판단불가: 위 유형으로 분류 어려움
            
            시설물 민원이면 subcategory를 가능한 한 구체적으로(휴게/운동/놀이, 녹지/위생/서비스, 통행/보호/도시 시설 등).
            
            [에러 코드 기준]
            정상 분석 가능하면 error_code는 null.
            
            E001_IMAGE_ANALYSIS_FAILED: 이미지 분석 자체가 실패한 경우
            E002_OBJECT_NOT_IDENTIFIED: 주요 객체를 식별할 수 없는 경우
            E003_IRRELEVANT_IMAGE: 민원과 관련 없는 이미지인 경우
            E004_CATEGORY_UNCLEAR: type/domain 분류가 불명확한 경우
            E005_LOW_IMAGE_QUALITY: 흐림, 어두움, 가림 등으로 판단이 어려운 경우
            E006_UNVERIFIABLE_CLAIM: 사용자의 주장과 이미지 증거를 연결하기 어려운 경우
            E007_PRIVACY_RISK: 얼굴, 번호판 등 개인정보 노출 가능성이 있는 경우
            E008_LOCATION_MISMATCH: 사용자 위치와 사진 메타 주소가 명확히 다른 경우
            
            [검색]
            keywords: 5~8개, 명사 중심, 일반어(문제, 민원, 사진) 금지.
            query: 1문장 30~50자. 위치는 입력이 있을 때만 포함.
            
            [출력 JSON 형식]
            {{
              "type": "",
              "domain": "",
              "subcategory": "",
              "summary": "",
              "objects": [],
              "error_code": null,
              "keywords": [],
              "query": ""
            }}
        """.strip()

    @staticmethod
    def _render_optional(value: str | None) -> str:
        if value is None:
            return "null"
        stripped = value.strip()
        return stripped if stripped else "null"
