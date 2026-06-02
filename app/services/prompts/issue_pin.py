from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.models.enum.ToneType import ToneType

ISSUE_PIN_CREATION_PROMPT = """
[역할]
너는 커뮤니티 민원 핀 문구 작성기다.
입력 데이터와 RAG 근거를 바탕으로 제목과 본문을 함께 생성한다.

[입력]
- 사용자 민원 내용: {user_text}
- 사용자 위치(주소): {user_location}
- 사용자 선택 톤: {tone}
- RAG 검색 질의들: {rag_queries}
- RAG 검색 근거: {retrieved_docs}

[최우선 규칙]
- 입력/근거에 없는 사실 생성 금지
- 위치 추측 금지
- 시간/원인/위법성 단정 금지
- 과장/비난/혐오/욕설/공격적 표현 금지
- RAG 문장 그대로 복사 금지
- 근거가 약하면 보수적으로 작성

[제목 공통 규칙]
- GPS 좌표(위도,경도 숫자 쌍) 출력 금지
- 제목에는 주소를 넣지 않는다 (시·군·구·동·읍·면·리·도로명·지번·번지·층/호수 등 위치 표기 전부 금지)
- 공문·민원·신고 접수문 느낌 금지 ("단속 요청", "제보", "조치 바랍니다" 등 딱딱한 표현 지양)
- 본문과 내용이 겹치더라도 제목은 더 짧고 선명하게 요약

[본문 공통 규칙]
- 본문에는 사용자 위치(주소)를 필요하면 자연스럽게 포함해도 된다
- 주소는 본문에서 상황 설명용으로만 사용하고, 제목으로 복사하지 않는다

[선택된 톤 규칙 — 제목·본문 모두 아래 톤에 맞게 작성]
{tone_style_rules}

[문체 규칙]
- 커뮤니티 글처럼 자연스럽고 간결하게 작성
- 정식 공문체/명령조 금지
- 이모지는 필요할 때만 문장당 최대 1개
- 본문 가독성을 최우선으로 작성 (한 문장 너무 길게 쓰지 말 것)
- 문단을 2~4줄로 적절히 나눠 읽기 쉽게 구성
- 핵심 문제와 요청 내용을 앞부분에 배치

[커뮤니티 게시용 작성 규칙]
- 민원 접수문이 아니라 "이웃에게 공유하는 글" 톤으로 작성
- 첫 줄에서 상황이 바로 보이게 작성
- 중간에는 실제 불편/체감 맥락을 짧게 설명
- 마지막은 함께 공감하거나 관심을 유도하는 문장으로 마무리
- 과한 훈계/비난/기관 대상 명령형 표현은 피하고, 제안형 문장 사용

[출력 규칙]
- JSON만 출력: {{"title": "...", "content": "..."}}
- 마크다운/설명문/코드블록 출력 금지
- 본문 길이 규칙 엄수: 한줄요약형만 짧게, 그 외 톤은 250~350자
"""

ISSUE_PIN_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "content"],
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
    },
}


def _tone_label(tone: ToneType | str) -> str:
    if isinstance(tone, ToneType):
        return tone.value
    return str(tone).strip() or ToneType.NONE.value


def _resolve_tone_type(tone: ToneType | str) -> ToneType:
    if isinstance(tone, ToneType):
        return tone
    text = str(tone).strip()
    if not text:
        return ToneType.NONE
    for member in ToneType:
        if text == member.value or text == member.name:
            return member
    return ToneType.NONE


_TONE_STYLE_RULES: dict[ToneType, str] = {
    ToneType.NONE: """
- 제목(15~42자): 동네 커뮤니티 게시판 제목처럼 한 줄, 짧고 자연스럽게. 이웃에게 말 걸듯 가볍게.
  예) "골목 불법주차, 통행 너무 힘들어요", "요즘 이 문제 자주 보이는 것 같아요"
- 본문(200~350자): 상황 설명과 공감·나눔의 균형. 2~4문단.
""".strip(),
    ToneType.ONE_LINE_SUMMARY: """
- 제목(15~30자): 본문 핵심을 한 줄 더 짧게 압축. 군더더기 없이 핵심만.
  예) "골목 불법주차로 통행 불편", "밤마다 소음 때문에 잠 설쳐요"
- 본문(1문장, 100자 내외): 제목과 같은 핵심을 한 문장으로만 풀어쓰기.
""".strip(),
    ToneType.SITUATION_DESCRIPTION: """
- 제목(15~42자): 지금 어떤 상황인지 바로 느껴지게. "요즘 ~", "~인 것 같아요", "~때문에" 등 상황 중심.
  예) "요즘 골목 불법주차가 심해진 것 같아요", "쓰레기가 쌓여서 걱정돼요"
- 본문(250~350자): 언제·어디서·어떤 상황인지 차분히 설명. 사실 중심, 2~4문단.
""".strip(),
    ToneType.IMPROVEMENT_REQUEST: """
- 제목(15~42자): 부드러운 바람·제안 톤. "~개선되면 좋겠어요", "함께 ~해볼까요?" 등.
  예) "불법주차 문제, 함께 개선해보면 좋겠어요", "골목 정리가 필요할 것 같아요"
- 본문(250~350자): 문제 인식 + 개선 제안·부탁 중심. 명령조·훈계 금지, 2~4문단.
""".strip(),
    ToneType.URGENT_REQUEST: """
- 제목(15~42자): 빠른 확인·관심이 필요하다는 느낌. 과장·공포 조장·이모지 금지.
  예) "위험해 보여서 빨리 확인됐으면 해요", "통행 사고 우려가 있어요"
- 본문(250~350자): 왜 빨리 확인이 필요한지 차분히 설명. 과장 금지, 이모지 금지, 2~4문단.
""".strip(),
    ToneType.DISCOMFORT_COMPLAINT: """
- 제목(15~42자): 체감 불편·감정을 절제해서 표현. "~너무 불편해요", "~때문에 힘들어요".
  예) "불법주차 때문에 매일 통행이 힘들어요", "소음 때문에 스트레스받아요"
- 본문(250~350자): 실제로 겪는 불편과 감정을 솔직하되 과하지 않게. 2~4문단.
""".strip(),
}


def format_tone_style_rules(tone: ToneType | str) -> str:
    resolved = _resolve_tone_type(tone)
    label = _tone_label(resolved)
    body = _TONE_STYLE_RULES.get(resolved, _TONE_STYLE_RULES[ToneType.NONE])
    return f"선택 톤: {label}\n{body}"


def format_user_text_for_pin(*, title: str, content: str) -> str:
    """핀 프롬프트 [입력]의 user_text 슬롯용. VLM 단계와 동일한 결합 규칙을 쓸 수 있다."""
    return f"title:{title.strip()}\ncontent:{content.strip()}\n"


def format_retrieved_docs_for_pin(
    rag_hits: Sequence[Mapping[str, Any]],
    *,
    rag_query: str | None = None,
    rag_queries: Sequence[str] | None = None,
    rag_filters_applied: bool | None = None,
    text_preview_chars: int = 180,
) -> str:
    """
    RAG 검색 근거 블록. 모델이 문장을 복사하지 않고 톤·표현만 참고하도록,
    청크 본문은 짧게 잘라 요지만 보이게 한다.
    """
    lines: list[str] = []
    if rag_queries:
        query_lines = [q.strip() for q in rag_queries if isinstance(q, str) and q.strip()]
        if query_lines:
            lines.append("[RAG 검색 질의 목록]")
            lines.extend(f"- {q}" for q in query_lines[:4])
            lines.append("")
    if rag_query is not None and str(rag_query).strip():
        lines.append("[RAG 검색에 사용한 쿼리]")
        lines.append(str(rag_query).strip())
        lines.append("")
    if rag_filters_applied is not None:
        lines.append(f"[메타데이터 필터 적용 여부] {rag_filters_applied}")
        lines.append("")
    lines.append("[검색 근거 청크 — 문장 전체 복사 금지, 스타일·현실 표현 참고만]")
    if not rag_hits:
        lines.append("(검색 결과 없음)")
        return "\n".join(lines)

    for i, hit in enumerate(rag_hits[:5], start=1):
        text = hit.get("text")
        text_s = text if isinstance(text, str) else ""
        preview = text_s.strip()
        if len(preview) > text_preview_chars:
            preview = preview[:text_preview_chars].rstrip() + "…"
        score = hit.get("score")
        meta = hit.get("metadata")
        meta_s = ""
        if isinstance(meta, dict) and meta:
            parts = [f"{k}={v}" for k, v in meta.items() if v is not None]
            meta_s = " | ".join(parts[:4])
        lines.append(f"--- 항목 {i} (유사도: {score}) ---")
        if meta_s:
            lines.append(f"메타: {meta_s}")
        lines.append(f"요지: {preview or '(본문 없음)'}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_issue_pin_prompt(
    *,
    user_text: str,
    user_location: str | None,
    tone: ToneType | str,
    rag_hits: Sequence[Mapping[str, Any]],
    rag_queries: Sequence[str] | None = None,
    rag_query: str | None = None,
    rag_filters_applied: bool | None = None,
) -> str:
    """핀 생성 LLM에 넣을 단일 프롬프트 문자열."""
    retrieved = format_retrieved_docs_for_pin(
        rag_hits,
        rag_queries=rag_queries,
        rag_query=rag_query,
        rag_filters_applied=rag_filters_applied,
    )
    return ISSUE_PIN_CREATION_PROMPT.format(
        user_text=user_text.strip(),
        user_location=(user_location or "null"),
        tone=_tone_label(tone),
        tone_style_rules=format_tone_style_rules(tone),
        rag_queries=json.dumps(list(rag_queries or []), ensure_ascii=False),
        retrieved_docs=retrieved,
    )


def build_issue_pin_prompt_from_pipeline_bundle(
    bundle: Mapping[str, Any],
    *,
    tone: ToneType | str | None = None,
) -> str:
    """
    `create_issue_pin` 파이프라인이 돌려주는 dict 형태에 맞춘 빌더.

    기대 키:
      - issue: { "title", "content", "tone" (optional) }
      - rag_hits: list[dict] (각 원소: text, score, metadata)
      - rag_queries, rag_query, rag_filters_applied: 선택
    """
    issue = bundle.get("issue") or {}
    if not isinstance(issue, Mapping):
        issue = {}

    title = issue.get("title", "")
    content = issue.get("content", "")
    title_s = title if isinstance(title, str) else str(title)
    content_s = content if isinstance(content, str) else str(content)
    user_text = format_user_text_for_pin(title=title_s, content=content_s)

    eff_tone: ToneType | str = ToneType.NONE
    if tone is not None:
        eff_tone = tone
    else:
        raw_t = issue.get("tone")
        if isinstance(raw_t, ToneType):
            eff_tone = raw_t
        elif isinstance(raw_t, str) and raw_t.strip():
            eff_tone = raw_t

    rag_raw = bundle.get("rag_hits") or []
    if isinstance(rag_raw, list):
        rag_hits: list[Mapping[str, Any]] = [h for h in rag_raw if isinstance(h, Mapping)]
    else:
        rag_hits = []

    rqs = bundle.get("rag_queries")
    if isinstance(rqs, list):
        rag_queries: list[str] = [q for q in rqs if isinstance(q, str)]
    else:
        rag_queries = []

    rq = bundle.get("rag_query")
    rag_query = rq if isinstance(rq, str) else None

    fa = bundle.get("rag_filters_applied")
    rag_filters_applied: bool | None = fa if isinstance(fa, bool) else None

    loc = issue.get("location")
    user_location = loc if isinstance(loc, str) and loc.strip() else None

    return build_issue_pin_prompt(
        user_text=user_text,
        user_location=user_location,
        tone=eff_tone,
        rag_hits=rag_hits,
        rag_queries=rag_queries,
        rag_query=rag_query,
        rag_filters_applied=rag_filters_applied,
    )


__all__ = [
    "ISSUE_PIN_CREATION_PROMPT",
    "ISSUE_PIN_OUTPUT_SCHEMA",
    "format_tone_style_rules",
    "format_user_text_for_pin",
    "format_retrieved_docs_for_pin",
    "build_issue_pin_prompt",
    "build_issue_pin_prompt_from_pipeline_bundle",
]
