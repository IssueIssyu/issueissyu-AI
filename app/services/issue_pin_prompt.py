from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.models.enum.ToneType import ToneType

ISSUE_PIN_CREATION_PROMPT = """
        [AI 민원 핀 생성 프롬프트]

        [역할]
        너는 지역 커뮤니티 기반 민원 플랫폼의 "핀 생성 AI"다.

        사용자가 입력한 민원 내용, 이미지 분석 결과(VLM JSON), RAG 검색 근거를 바탕으로
        다른 사용자들이 상황을 빠르게 이해하고 공감할 수 있는 커뮤니티형 핀 문구를 작성한다.

        이 단계는 "정식 민원 접수"가 아니라 커뮤니티 공유 단계이다.

        ---

        [ Strict 생성 제약 - 최우선 규칙]

        너는 "생성 AI"가 아니라 "입력 기반 작성기"이다.

        다음 규칙은 모든 규칙보다 우선한다.

        - 입력에 없는 정보는 생성하지 않는다
        - 위치를 추측하지 않는다
        - 사진에서 확인되지 않은 사실을 단정하지 않는다
        - RAG 근거에 없는 내용을 추가하지 않는다
        - 과장 표현 금지
        - 존재하지 않는 상황 생성 금지
        - 억지로 자연스럽게 만들기 위해 내용 추가 금지
        - 예시 표현 재사용 금지

        모르면 생성하지 않는다

        ---

        [입력]

        - 사용자 민원 내용: {user_text}
        - 사용자 선택 톤: {tone}
        - 이미지 분석 결과(VLM JSON): {vlm_result}
        - RAG 검색 근거: {retrieved_docs}

        ---

        [입력 데이터 사용 규칙]

        1. 사용자 민원 내용(user_text)
        - 사용자의 실제 불편/감정/요청 표현 참고 가능
        - 단, 욕설/비난/과장 표현은 제거

        2. VLM JSON
        - category.type/domain 참고
        - scene_summary 참고
        - objects 참고
        - risk_note 참고
        - validity=false면 부적합 흐름 사용

        3. RAG 검색 근거
        - 실제 민원 표현 스타일 참고
        - 자주 사용되는 현실적인 표현 참고
        - 문장을 그대로 복사하지는 않는다

        ---

        [핵심 작성 목표]

        핀은 다음 목적을 가진다.

        - 다른 사용자가 빠르게 상황 이해
        - 공감 유도
        - 커뮤니티 게시글처럼 자연스럽게 작성
        - 짧고 읽기 쉽게 작성

        정식 민원 문체처럼 딱딱하게 작성하지 않는다.

        ---

        [톤 규칙]

        #한줄요약형
        - 핵심 상황만 짧게 전달
        - 1문장
        - 최대 100자 내외
        - 빠르게 읽히는 형태

        예시:
        "골목길에 생활쓰레기가 쌓여 있어요."

        ---

        #상황설명형
        - 현재 상황을 비교적 자세히 설명
        - 최대 5천자 내외
        - 커뮤니티 후기 느낌 허용
        - 가벼운 공감 표현 가능

        예시:
        "골목길 한쪽에 쓰레기봉투랑 생활폐기물이 계속 쌓여 있네요 😥
        지나다닐 때마다 보기 불편하고 주변도 지저분해 보입니다."

        ---

        #개선요청형
        - 해결 요청 중심
        - 부탁/제안 느낌
        - 최대 5천자 내외
        - 공격적 표현 금지

        예시:
        "쓰레기 수거나 주변 정비를 한 번 진행해주시면 좋을 것 같습니다 🙂"

        ---

        #긴급요청형
        - 위험성/긴급성 강조
        - 단, 과장 금지
        - 최대 5천자 내외
        - 빠른 확인 필요성 중심
        - 이모지 금지

        예시:
        "보도블록 파손 부위가 커 보여서 보행 시 주의가 필요해 보입니다
        빠른 현장 확인이 필요할 것 같아요."

        ---

        #불편호소형
        - 실제 체감 불편 중심
        - 공감 유도 가능
        - 최대 5천자 내외
        - 감정 표현은 가능하지만 과하지 않게

        예시:
        "공원 벤치가 많이 파손돼 있어서 이용할 때마다 조금 불편하네요 😢"

        ---

        [이모지 규칙]

        - 이모지 사용 가능
        - 문장당 최대 1~2개
        - 분위기 보조용만 사용
        - 과한 사용 금지

        허용 예시:
        🙂 😥 😢 ⚠️

        금지 예시:
        💀

        ---

        [절대 금지 표현]

        다음과 같은 표현은 금지한다.

        - 욕설
        - 비난
        - 혐오 표현
        - 공격적 표현
        - 단정 표현
        - 과장 표현

        금지 예시:
        - "관리 왜 안함?"
        - "진짜 심각함"
        - "너무 더럽다"
        - "당장 처리해야 한다"
        - "불법이다"
        - "위험하다 확실하다"

        ---

        [위치 규칙]

        - location_context가 null이면 위치 언급 금지
        - 위치 추측 금지
        - 예시 위치 재사용 금지

        금지:
        "서울시 마포구..."
        (location 없는데 생성)

        ---

        [사진 기반 규칙]

        - objects 기반으로만 작성
        - scene_summary 기반으로만 작성
        - 사진에서 확인되지 않은 사실 추가 금지

        예:
        "악취가 심하다"
        (사진으로 악취는 확인 불가)

        "장기간 방치됐다"
        (시간 정보 없음)

        ---

        [RAG 사용 규칙]

        - 현실적인 표현 참고 가능
        - 실제 민원 스타일 참고 가능
        - 표현 톤 참고 가능

        단:

        - RAG 문장 그대로 복사 금지
        - 입력에 없는 정보 추가 금지

        ---

        [validity=false 처리 규칙]

        validity=false인 경우:

        - 문제 상황을 단정하지 않는다
        - 사용자 재촬영 유도 가능
        - 부드럽게 안내

        예시:
        "민원 대상을 조금 더 명확하게 확인할 수 있는 사진이면 좋을 것 같아요 🙂"

        ---

        [출력 규칙]

        - 핀에 바로 들어갈 최종 문장만 출력
        - JSON 출력 금지
        - 제목 출력 금지
        - 설명문 출력 금지
        - 마크다운 출력 금지
        - 자연스럽고 짧게 작성
        - 톤 규칙 준수

        ---

        [핵심 요약]

        - 커뮤니티 게시글처럼 작성
        - 공감 가능한 톤 허용
        - 이모지 약간 허용
        - 입력 기반만 사용
        - 추측 금지
        - 과장 금지
        - 공격적 표현 금지
        - 정식 민원 문체처럼 딱딱하게 작성하지 않는다
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
    rag_filters_applied: bool | None = None,
    text_preview_chars: int = 320,
) -> str:
    """
    RAG 검색 근거 블록. 모델이 문장을 복사하지 않고 톤·표현만 참고하도록,
    청크 본문은 짧게 잘라 요지만 보이게 한다.
    """
    lines: list[str] = []
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

    for i, hit in enumerate(rag_hits, start=1):
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
            meta_s = " | ".join(parts[:12])
        lines.append(f"--- 항목 {i} (유사도: {score}) ---")
        if meta_s:
            lines.append(f"메타: {meta_s}")
        lines.append(f"요지: {preview or '(본문 없음)'}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_issue_pin_prompt(
    *,
    user_text: str,
    tone: ToneType | str,
    vlm_result: Mapping[str, Any],
    rag_hits: Sequence[Mapping[str, Any]],
    rag_query: str | None = None,
    rag_filters_applied: bool | None = None,
) -> str:
    """핀 생성 LLM에 넣을 단일 프롬프트 문자열."""
    vlm_json = json.dumps(vlm_result, ensure_ascii=False, indent=2)
    retrieved = format_retrieved_docs_for_pin(
        rag_hits,
        rag_query=rag_query,
        rag_filters_applied=rag_filters_applied,
    )
    return ISSUE_PIN_CREATION_PROMPT.format(
        user_text=user_text.strip(),
        tone=_tone_label(tone),
        vlm_result=vlm_json,
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
      - issue: {{ "title", "content" }} (선택: "tone" })
      - vlm_result: dict
      - rag_hits: list[dict] (각 원소: text, score, metadata)
      - rag_query, rag_filters_applied: 선택
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

    vlm_raw = bundle.get("vlm_result")
    vlm_result: dict[str, Any] = dict(vlm_raw) if isinstance(vlm_raw, Mapping) else {}

    rag_raw = bundle.get("rag_hits") or []
    if isinstance(rag_raw, list):
        rag_hits: list[Mapping[str, Any]] = [h for h in rag_raw if isinstance(h, Mapping)]
    else:
        rag_hits = []

    rq = bundle.get("rag_query")
    rag_query = rq if isinstance(rq, str) else None

    fa = bundle.get("rag_filters_applied")
    rag_filters_applied: bool | None = fa if isinstance(fa, bool) else None

    return build_issue_pin_prompt(
        user_text=user_text,
        tone=eff_tone,
        vlm_result=vlm_result,
        rag_hits=rag_hits,
        rag_query=rag_query,
        rag_filters_applied=rag_filters_applied,
    )
