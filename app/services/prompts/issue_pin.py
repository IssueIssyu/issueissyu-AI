from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.models.enum.ToneType import ToneType

ISSUE_PIN_CREATION_PROMPT = """
[역할]
너는 커뮤니티 민원 핀 문구 작성기다.
입력 데이터와 RAG 근거를 바탕으로 최종 본문 1개만 생성한다.

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

[톤 규칙]
- 한줄요약형: 1문장, 100자 내외
- 상황설명형: 250~350자(약 300자), 상황 중심
- 개선요청형: 250~350자(약 300자), 부탁/제안 중심
- 긴급요청형: 250~350자(약 300자), 빠른 확인 필요성 강조, 과장 금지, 이모지 금지
- 불편호소형: 250~350자(약 300자), 체감 불편 + 절제된 감정 표현

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
- 최종 본문만 출력
- JSON/마크다운/제목/설명문 출력 금지
- 길이 규칙 엄수: 한줄요약형만 짧게, 그 외 톤은 250~350자
"""


def _tone_label(tone: ToneType | str) -> str:
    if isinstance(tone, ToneType):
        return tone.value
    return str(tone).strip() or ToneType.NONE.value


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
    "format_user_text_for_pin",
    "format_retrieved_docs_for_pin",
    "build_issue_pin_prompt",
    "build_issue_pin_prompt_from_pipeline_bundle",
]
