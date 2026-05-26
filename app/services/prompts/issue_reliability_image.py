from __future__ import annotations

from app.services.prompts.confidence_basis import (
    CONFIDENCE_BASIS_ARRAY_SCHEMA,
    CONFIDENCE_BASIS_JSON_EXAMPLE_WITH_IMAGE,
    CONFIDENCE_BASIS_PROMPT_BLOCK,
)

RELIABILITY_IMAGE_SCORING_GUIDE = """
[세부 평가 기준]
아래 4개 축(content, image, location, reference)을 각각 먼저 판단한 뒤 최종 점수를 정한다.

축별 판정 규칙:
- content: 제목/본문에 민원 대상, 문제 상황, 요청 의도가 명확하면 ok, 핵심이 빠지면 warn
- image: 사진에서 글과 같은 상황이 보이면 ok, 흐림/가림/원거리로 판단이 애매하면 warn
- location: 지도 위치와 사진 메타 주소/본문 장소가 모순 없으면 ok, 다른 지역 가능성이 있으면 warn
- reference: 참고 사례와 주제/조치 맥락이 유사하면 ok, 관련성이 약하면 warn
- caution: 애매한 근거가 있으면 warn으로 1개 이상 작성, 없으면 skip

점수 가이드:
- 0.85~1.00: 4개 핵심 축 중 3개 이상이 ok, 명확한 모순 없음
- 0.65~0.84: 핵심 축에 ok/warn이 혼재하나 전체 맥락은 대체로 일치
- 0.40~0.64: 애매한 요소가 많아 추가 확인이 필요
- 0.00~0.39: 핵심 근거 부족 또는 상충 정황 다수

감점 규칙:
- 사진 품질이 낮아 대상 식별이 어려우면 -0.10~-0.25
- 위치 불일치 가능성이 크면 -0.10~-0.20
- 텍스트와 사진의 대상이 다르게 보이면 -0.20 이상
- 참고 사례가 거의 무관하면 -0.05~-0.15

주의:
- 위치/사진 정보가 비어 있다는 이유만으로 자동 저점수 처리하지 않는다.
- 확신이 없을 때는 단정 대신 warn과 보수적 점수를 사용한다.
""".strip()


def build_issue_reliability_image_prompt(
    *,
    user_text: str,
    user_location: str | None,
    user_address: str | None,
    photo_address: str | None,
    per_image_slot_text: str,
    rag_context_block: str,
) -> str:
    ul = user_location if user_location and user_location.strip() else "null"
    ua = user_address if user_address and user_address.strip() else "null"
    pa = photo_address if photo_address and photo_address.strip() else "null"
    rag = rag_context_block.strip() if rag_context_block.strip() else "(검색 결과 없음)"

    return f"""
[역할]
너는 지자체 민원 제보의 신뢰도를 빠르게 평가하는 AI다.
민원 분류(category/type/domain)나 상세 객체 추출은 하지 않는다.

[입력]
사용자 민원 텍스트(고정 형식):
{user_text.strip()}

사용자 핀 GPS(위도,경도 문자열, null 가능): {ul}
사용자 핀 행정 주소(역지오코딩, null 가능): {ua}
사진 메타데이터 주소(없을 수 있음): {pa}
이미지 슬롯 정보:
{per_image_slot_text}

[참고 사례 — 내부 참고만, 문장 복사·사실 추가 금지]
{rag}

[신뢰도 점수]
confidence_score: 0.0~1.0. 글·사진·위치·참고 사례의 일관성을 종합한다.
위치 정보가 부족해도 그것만으로 과도하게 낮추지 않는다.
{RELIABILITY_IMAGE_SCORING_GUIDE}

{CONFIDENCE_BASIS_PROMPT_BLOCK}

[출력]
반드시 JSON만 출력한다.
{{
  "confidence_score": 0.0,
  {CONFIDENCE_BASIS_JSON_EXAMPLE_WITH_IMAGE}
}}
""".strip()


RELIABILITY_IMAGE_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["confidence_score", "confidence_basis"],
    "properties": {
        "confidence_score": {"type": "number"},
        "confidence_basis": CONFIDENCE_BASIS_ARRAY_SCHEMA,
    },
}

