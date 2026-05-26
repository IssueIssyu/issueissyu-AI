from __future__ import annotations

from app.services.prompts.confidence_basis import (
    CONFIDENCE_BASIS_ARRAY_SCHEMA,
    CONFIDENCE_BASIS_JSON_EXAMPLE_TEXT_ONLY,
    CONFIDENCE_BASIS_PROMPT_BLOCK,
)

RELIABILITY_TEXT_SCORING_GUIDE = """
[세부 평가 기준]
이미지가 없는 텍스트 검증 모드다. content, location, reference를 중심으로 평가한다.

축별 판정 규칙:
- content: 신고 대상/문제/요청이 글에서 일관되게 읽히면 ok, 핵심이 빠지면 warn
- location: GPS·주소·본문 장소 표현이 서로 모순 없으면 ok, 불명확/상충 가능성이 있으면 warn
- reference: 참고 사례와 주제/처리 방향이 유사하면 ok, 연결성이 약하면 warn
- image: 항상 skip, text=""
- caution: 불확실한 점이 있으면 warn으로 작성, 없으면 skip

점수 가이드:
- 0.80~1.00: content/location/reference 중 2개 이상이 명확히 ok
- 0.60~0.79: 핵심 맥락은 맞지만 일부 정보가 모호
- 0.35~0.59: 정보 부족으로 추가 확인 필요
- 0.00~0.34: 핵심 사실이 부족하거나 서로 충돌

감점 규칙:
- 위치 단서가 상충하거나 불일치 가능성이 크면 -0.10~-0.20
- 참고 사례와 주제 연결이 약하면 -0.05~-0.15
- 본문이 지나치게 짧거나 핵심 정보 누락 시 -0.10~-0.25

주의:
- 이미지가 없다는 이유만으로 자동 저점수 처리하지 않는다.
- 모르면 추측하지 말고 warn/skip으로 처리한다.
""".strip()


def build_issue_reliability_text_prompt(
    *,
    user_text: str,
    user_location: str | None,
    user_address: str | None,
    rag_context_block: str,
) -> str:
    ul = user_location if user_location and user_location.strip() else "null"
    ua = user_address if user_address and user_address.strip() else "null"
    rag = rag_context_block.strip() if rag_context_block.strip() else "(검색 결과 없음)"

    return f"""
[역할]
너는 지자체 민원 제보의 신뢰도를 평가하는 AI다.
결과 근거(confidence_basis)는 제보를 올린 일반 시민이 앱에서 읽는다. 쉬운 말·존댓말로 쓴다.
업로드 이미지는 없다. 사용자 텍스트, 지도 위치, 참고 사례만으로 신뢰도를 판단한다.

[입력]
사용자 민원 텍스트(고정 형식):
{user_text.strip()}

사용자 핀 GPS(위도,경도 문자열, null 가능): {ul}
사용자 핀 행정 주소(역지오코딩, null 가능): {ua}

[참고 사례 — 내부 참고만, 문장 복사·사실 추가 금지. 근거 문장에 'RAG' 등 기술 용어 쓰지 말 것]
{rag}

[신뢰도 점수]
confidence_score: 0.0~1.0. 텍스트·위치·RAG 맥락의 일관성을 종합한다.
주소가 없어도 위치 부족만으로 과도하게 낮추지 않는다.
{RELIABILITY_TEXT_SCORING_GUIDE}

{CONFIDENCE_BASIS_PROMPT_BLOCK}
이미지는 없으므로 image 축은 반드시 status=skip, text="" 이다.

[출력]
반드시 JSON만 출력한다.
{{
  "confidence_score": 0.0,
  {CONFIDENCE_BASIS_JSON_EXAMPLE_TEXT_ONLY}
}}
""".strip()


RELIABILITY_TEXT_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["confidence_score", "confidence_basis"],
    "properties": {
        "confidence_score": {"type": "number"},
        "confidence_basis": CONFIDENCE_BASIS_ARRAY_SCHEMA,
    },
}
