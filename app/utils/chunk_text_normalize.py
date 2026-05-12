from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# 줄 시작이 이 접두어이면 제외 (None이면 이 기본값 사용)
# TL1: [민원 …] 줄은 임베딩 텍스트에서만 제거. 부서 값은 JSONL 행의 category, subcategory.. → build_chunk_metadata 로
DEFAULT_NORMALIZE_SKIP_PREFIXES: tuple[str, ...] = (
    "[출처 기관]",
    "[상담 분류]",
    "[상담 일자]",
    "[상담 내용]",
    "[민원 대분류]",
    "[민원 소분류]",
    "[민원 유형]",
    "[담당 부서]",
    "[민원 내용]",
    "제목 :",
)

# 이 줄에서 잘리면 해당 줄과 이후 전부 제거
DEFAULT_FOOTER_LINE_PREFIXES: tuple[str, ...] = (
    "끝.",
    "[본 회신내용",
)

# 행 전체를 버리는 QnA 답변 서식용 섹션 제목 (질의 요지 등)
DEFAULT_QNA_SECTION_HEADER_LINES: frozenset[str] = frozenset(
    {
        "□ 질의 요지",
        "□질의 요지",
        "□ 답변 내용",
        "□답변 내용",
    }
)

# 행 전체가 일치할 때만 제거 (고정 인사말 — 패턴이 확실한 문장만 추가)
DEFAULT_QNA_GREETING_EXACT_LINES: frozenset[str] = frozenset(
    {
        "안녕하십니까? 평소 국토 교통행정에 관심과 애정을 가져 주신 점 깊이 감사드리며, 선생님께서 질의하신 사항에 대하여 아래와 같이 답변드립니다.",
    }
)

_QA_LINE_PREFIX_RE = re.compile(r"^[QqAa]\s*:\s*")
_STRIP_LEADING_BULLETS_RE = re.compile(r"^[□ㅇ\s]+")


def _strip_leading_bullet_marks(line: str) -> str:
    #줄 선두의 문자 및 인접 공백만 제거. 본문은 유지
    return _STRIP_LEADING_BULLETS_RE.sub("", line)


def load_skip_line_prefixes(path: Path) -> tuple[str, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"normalize 설정은 JSON 객체여야 함: {path}")
    raw = data.get("skip_line_prefixes")
    if raw is None:
        raw = data.get("skip_prefixes")
    if raw is None:
        raise ValueError(
            f"normalize 설정에 skip_line_prefixes 또는 skip_prefixes 배열이 필요함: {path}"
        )
    if not isinstance(raw, list):
        raise ValueError(f"skip_line_prefixes는 문자열 배열이어야 함: {path}")
    return tuple(str(x) for x in raw)


def normalize_chunk(
    chunk_text: str,
    skip_line_prefixes: Optional[tuple[str, ...]] = None,
    footer_line_prefixes: Optional[tuple[str, ...]] = None,
    *,
    qna_section_headers: Optional[frozenset[str]] = None,
    qna_greeting_exact_lines: Optional[frozenset[str]] = None,
) -> str:
    """QnA/TL1 청크 공통: 메타 줄 제거 + 푸터 이후 절단

    QnA 본문: Q:/A: 라벨 불릿 접두 제거, 질의/답변 섹션 제목 줄 삭제,
    고정 인사말(전체 행 일치)만 삭제.

    footer_line_prefixes: None이면 DEFAULT_FOOTER_LINE_PREFIXES를 사용하고,
    추가로 행 전체가 정확히 "끝"인 경우도 푸터로 간주해 절단한다. ()이면 푸터 절단을 전부 끔
    """
    raw = chunk_text.strip()
    if not raw:
        return ""

    prefixes = (
        DEFAULT_NORMALIZE_SKIP_PREFIXES
        if skip_line_prefixes is None
        else skip_line_prefixes
    )
    default_footer = footer_line_prefixes is None
    if default_footer:
        footers = DEFAULT_FOOTER_LINE_PREFIXES
    else:
        footers = footer_line_prefixes

    section_drop = (
        DEFAULT_QNA_SECTION_HEADER_LINES
        if qna_section_headers is None
        else qna_section_headers
    )
    greeting_drop = (
        DEFAULT_QNA_GREETING_EXACT_LINES
        if qna_greeting_exact_lines is None
        else qna_greeting_exact_lines
    )

    cleaned_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if footers:
            if default_footer and stripped == "끝":
                break
            if stripped.startswith(footers):
                break
        if prefixes and stripped.startswith(prefixes):
            continue

        after_qa = _QA_LINE_PREFIX_RE.sub("", stripped, count=1)
        if stripped in section_drop or after_qa in section_drop:
            continue

        after_bullets = _strip_leading_bullet_marks(after_qa)
        if not after_bullets or after_bullets in greeting_drop:
            continue

        cleaned_lines.append(after_bullets)

    return "\n".join(cleaned_lines).strip()
