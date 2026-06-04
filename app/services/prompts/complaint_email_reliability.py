from __future__ import annotations

from app.schemas.ComplaintEmailDTO import ComplaintEmailRagHit, ComplaintEmailVlmOutput
from app.services.prompts.confidence_basis import (
    CONFIDENCE_BASIS_ARRAY_SCHEMA,
    CONFIDENCE_BASIS_JSON_EXAMPLE_WITH_IMAGE,
    CONFIDENCE_BASIS_PROMPT_BLOCK,
)
from app.services.prompts.issue_reliability_image import RELIABILITY_IMAGE_SCORING_GUIDE

COMPLAINT_RELIABILITY_RAG_TOP_K = 5

COMPLAINT_RELIABILITY_CROSS_CHECK = """
[교차 검증 — 반드시 수행]
평가 순서: ① 제목·본문 ② 첨부 사진 ③ 청원 분석(type/domain/summary/objects) ④ 위치 ⑤ 참고 사례.
- content/image/location/reference 4개 핵심 축을 각각 판정한 뒤 confidence_score를 정한다. 애매하면 warn, 해당 없을 때만 skip.
- 글의 민원 대상·행위와 사진 속 상황이 다르게 보이면 image=warn, confidence_score에서 0.20 이상 감점.
- 청원 분석 type/domain과 사진·본문이 명백히 어긋나면 reference 또는 content=warn, risk_note에 요약.
- 사진 메타 주소와 핀 GPS·행정 주소가 다른 지역으로 보이면 location=warn, risk_note에 위치 확인 필요를 적는다.
- 사진 메타 주소가 없으면 location은 not_checked에 가깝게 판단하되, 위치 부족만으로 점수를 과도하게 깎지 않는다.
- 번호판·얼굴·전화번호 등 개인정보가 보이거나 추정되면 caution=warn, risk_note에 개인정보 주의를 적는다.
- 참고 사례와 주제가 거의 무관하면 reference=warn.

validity 규칙(보수적):
- true: 핵심 축 3개 이상 ok, 명백한 상충 없음, 민원 대상·상황·요청이 담당 검토 가능한 수준.
- false: 글·사진이 다른 제보로 보이거나, 핵심 정보 누락·상충이 커서 추가 확인이 필수.

risk_note: 위 규칙에서 warn·상충·개인정보·위치 불일치 등 담당자가 알아야 할 점만 1~2문장. 없으면 null.
""".strip()

COMPLAINT_EMAIL_RELIABILITY_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "confidence_score",
        "confidence_basis",
        "scene_summary",
        "risk_note",
        "validity",
        "notification_subject",
        "notification_summary",
    ],
    "properties": {
        "confidence_score": {"type": "number"},
        "confidence_basis": CONFIDENCE_BASIS_ARRAY_SCHEMA,
        "scene_summary": {"type": "string"},
        "risk_note": {"type": "string", "nullable": True},
        "validity": {"type": "boolean"},
        "notification_subject": {"type": "string"},
        "notification_summary": {"type": "string"},
    },
}


def build_complaint_rag_context_block(
    hits: list[ComplaintEmailRagHit],
    *,
    limit: int = COMPLAINT_RELIABILITY_RAG_TOP_K,
) -> str:
    lines: list[str] = []
    for hit in hits[:limit]:
        text = (hit.text or "").strip()
        if not text:
            continue
        snippet = text[:400] + ("…" if len(text) > 400 else "")
        lines.append(f"- {snippet}")
    if not lines:
        return "(검색 결과 없음)"
    return "\n".join(lines)


def _render_complaint_vlm_context(vlm: ComplaintEmailVlmOutput | None) -> str:
    if vlm is None:
        return "(청원 분석 없음)"
    objects = ", ".join(vlm.objects[:6]) if vlm.objects else "없음"
    return (
        f"type: {vlm.type}\n"
        f"domain: {vlm.domain}\n"
        f"subcategory: {vlm.subcategory or 'null'}\n"
        f"summary: {vlm.summary or 'null'}\n"
        f"objects: {objects}"
    )


def build_complaint_email_reliability_prompt(
    *,
    user_text: str,
    user_location: str | None,
    user_address: str | None,
    photo_address: str | None,
    per_image_slot_text: str,
    rag_context_block: str,
    complaint_vlm: ComplaintEmailVlmOutput | None,
    department: str | None,
) -> str:
    ul = user_location if user_location and user_location.strip() else "null"
    ua = user_address if user_address and user_address.strip() else "null"
    pa = photo_address if photo_address and photo_address.strip() else "null"
    rag = rag_context_block.strip() if rag_context_block.strip() else "(검색 결과 없음)"
    dept = department.strip() if isinstance(department, str) and department.strip() else "미지정"
    vlm_ctx = _render_complaint_vlm_context(complaint_vlm)

    return f"""
[역할]
지자체 민원 청원 알림 메일용 신뢰도 평가 및 알림 문구 작성 AI다.
이미지·이슈 핀·청원 분석·참고 사례를 종합해 신뢰도와 담당 부서용 알림 제목·요약을 만든다.
알림 문구 작성보다 신뢰도·교차 검증을 우선한다. 확신 없으면 보수적으로 warn·낮은 점수를 사용한다.

[입력]
사용자 민원 텍스트(고정 형식):
{user_text.strip()}

사용자 핀 GPS(위도,경도 문자열, null 가능): {ul}
사용자 핀 행정 주소(역지오코딩, null 가능): {ua}
사진 메타데이터 주소(없을 수 있음): {pa}
이미지 슬롯 정보:
{per_image_slot_text}

[청원 분석 결과 — 사실 추가 금지, 요약·알림 문구 보강만]
{vlm_ctx}

[추천 담당 부서]
{dept}

[참고 사례 — 내부 참고만, 문장 복사·사실 추가 금지]
{rag}

[신뢰도 점수]
confidence_score: 0.0~1.0. 글·사진·위치·참고 사례의 일관성을 종합한다.
위치 정보가 부족해도 그것만으로 과도하게 낮추지 않는다.
{RELIABILITY_IMAGE_SCORING_GUIDE}

{CONFIDENCE_BASIS_PROMPT_BLOCK}

{COMPLAINT_RELIABILITY_CROSS_CHECK}

[알림 메일 문구]
notification_subject:
- 50자 이내(공백 포함)
- `[민원]` 또는 `[민원 자동 생성]` 접두 허용
- 핵심 쟁점·대상·추천 담당 부서({dept})를 간결히 반영
- 개인정보·번호판·얼굴 식별 정보 금지
- 이슈 핀 제목(title: 줄)은 그대로 인용·노출하지 않는다

notification_summary:
- 3~5문장, 행정 담당자 대상 존댓말
- 【민원 요약】에 그대로 들어갈 본문
- 감정·비난·위법 단정·개인정보 금지
- 청원 분석 summary·사진에서 확인된 사실만 사용
- 이슈 핀 제목(title: 줄)은 그대로 인용·노출하지 않는다

scene_summary: 사진 기반 상황 1~2문장(내부 참고, 감정 제거)

[출력]
반드시 JSON만 출력한다.
{{
  "confidence_score": 0.0,
  {CONFIDENCE_BASIS_JSON_EXAMPLE_WITH_IMAGE},
  "scene_summary": "",
  "risk_note": null,
  "validity": true,
  "notification_subject": "",
  "notification_summary": ""
}}
""".strip()
