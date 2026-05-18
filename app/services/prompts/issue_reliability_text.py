from __future__ import annotations

from app.services.prompts.confidence_basis import (
    CONFIDENCE_BASIS_ARRAY_SCHEMA,
    CONFIDENCE_BASIS_JSON_EXAMPLE_TEXT_ONLY,
    CONFIDENCE_BASIS_PROMPT_BLOCK,
)


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
