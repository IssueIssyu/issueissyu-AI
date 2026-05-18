from __future__ import annotations

import re
from typing import Any

from app.services.prompts.confidence_basis import CONFIDENCE_BASIS_AXES

_INLINE_BULLET_SPLIT = re.compile(r"\s+-\s+")

AXIS_ORDER: tuple[str, ...] = CONFIDENCE_BASIS_AXES

# 시민용 실패 안내 (confidence_content). 기술·개발 용어 없음.
FAILED_RELIABILITY_BASIS = (
    "- 지금은 이 제보에 대한 AI 검토 결과를 불러오지 못했어요.\n"
    "- 잠시 후 다시 열어보시거나, 사진과 글이 잘 보이는지 확인해 주세요."
)

FAILED_RELIABILITY_DETECT_PHRASES = (
    "AI 검토 결과를 불러오지 못했",
    "신뢰도 분석을 완료하지 못했습니다",
)

_USER_FACING_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bEXIF\b", "사진 정보"),
    (r"메타데이터", "사진에 남은 위치 정보"),
    (r"\bRAG\b", "유사 사례"),
    (r"\bGPS\b", "지도 위치"),
    (r"역지오코딩", "주소 확인"),
    (r"핀\s*위치", "지도에 표시한 위치"),
    (r"\b핀\b", "지도에 표시한 위치"),
    (r"검색\s*결과", "참고 사례"),
    (r"confidence_score", "신뢰도"),
    (r"confidence_basis", "검토 내용"),
    (r"VLM", "사진 분석"),
    (r"JSON", ""),
    (r"메타\s*주소", "사진을 찍은 곳의 주소"),
    (r"사진\s*메타", "사진"),
)

_LOCATION_MESSAGE_USER_FACING: dict[str, str] = {
    "matched": "지도에 표시한 위치와 사진을 찍은 곳이 잘 맞아 보입니다.",
    "same_area": "지도에 표시한 위치와 사진을 찍은 곳이 같은 동네 수준으로 보입니다.",
    "different_area": "지도에 표시한 위치와 사진을 찍은 곳이 다를 수 있어요. 한번 더 확인해 주세요.",
    "not_checked": "사진에 위치 정보가 없어, 사진 촬영 장소는 따로 비교하지 않았어요.",
    "unknown": "사진과 지도 위치가 같은지는 확실히 말씀드리기 어려워요.",
}


def is_failed_reliability_content(content: str | None) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    if text == FAILED_RELIABILITY_BASIS.strip():
        return True
    return any(phrase in text for phrase in FAILED_RELIABILITY_DETECT_PHRASES)


def sanitize_user_facing_basis_text(text: str) -> str:
    """한 줄 문장용. 줄바꿈은 건드리지 않는다."""
    out = text.strip()
    if not out:
        return ""
    for pattern, replacement in _USER_FACING_REPLACEMENTS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    return out


def normalize_display_line_breaks(text: str) -> str:
    """앱 표시용: 실제 줄바꿈 문자로 통일하고 bullet마다 한 줄씩 정리."""
    if not text:
        return ""
    normalized = text.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw in normalized.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("-") and "- " in line:
            for part in _split_inline_bullets(line):
                lines.append(part)
        elif line.startswith("-"):
            lines.append(line)
        else:
            lines.append(f"- {line.lstrip('-•*').strip()}")
    return "\n".join(lines)


def confidence_intro_for_score(score: float) -> str:
    if score >= 0.75:
        return "제출하신 글·사진·위치 정보가 서로 잘 맞는 편으로 보여요."
    if score >= 0.45:
        return "전반적으로 이해하기 쉬운 제보예요. 아래 내용을 함께 참고해 주세요."
    return "확인이 더 필요해 보이는 제보예요. 아래 내용을 참고해 주세요."


def format_confidence_content_for_user(*, score: float, basis_markdown: str) -> str:
    intro = confidence_intro_for_score(score)
    body = normalize_display_line_breaks(basis_markdown) if basis_markdown else ""
    if body:
        return f"{intro}\n{body}"
    return intro


def _preprocess_basis_text(text: str) -> str:
    return text.replace("\\n", "\n").strip()


def _split_inline_bullets(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return []
    if not stripped.startswith("-") and "- " not in stripped:
        return [f"- {stripped.lstrip('-•*').strip()}"]

    parts = _INLINE_BULLET_SPLIT.split(stripped)
    bullets: list[str] = []
    for part in parts:
        body = part.strip().lstrip("-•*").strip()
        if body:
            bullets.append(f"- {body}")
    return bullets


def normalize_confidence_basis_markdown(value: object, *, max_chars: int = 2000) -> str:
    """레거시: 모델이 markdown 문자열만 준 경우."""
    if not isinstance(value, str):
        return ""
    text = _preprocess_basis_text(value)
    if not text:
        return ""

    if "\n" not in text and text.count("- ") > 1:
        text = _INLINE_BULLET_SPLIT.sub("\n- ", text)
        if not text.startswith("- "):
            text = f"- {text.lstrip('-').strip()}"

    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append("\n".join(current))
            current = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        for bullet in _split_inline_bullets(line):
            sanitized = sanitize_user_facing_basis_text(bullet.lstrip("- ").strip())
            if sanitized:
                current.append(f"- {sanitized}")
    flush()

    if not blocks:
        return ""

    out = "\n".join(blocks)
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return normalize_display_line_breaks(out)


def _coerce_basis_items(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        axis = str(raw.get("axis") or "").strip()
        if axis not in AXIS_ORDER:
            continue
        status = str(raw.get("status") or "skip").strip().lower()
        if status not in {"ok", "warn", "skip"}:
            status = "skip"
        text = sanitize_user_facing_basis_text(str(raw.get("text") or ""))
        items.append({"axis": axis, "status": status, "text": text})
    return items


def render_confidence_basis_markdown(
    items: list[dict[str, str]],
    *,
    has_images: bool = True,
    max_chars: int = 2000,
) -> str:
    by_axis = {item["axis"]: item for item in items}
    bullets: list[str] = []

    for axis in AXIS_ORDER:
        if axis == "image" and not has_images:
            continue
        item = by_axis.get(axis)
        if item is None:
            continue
        if item["status"] == "skip" or not item["text"]:
            continue
        bullets.append(f"- {item['text']}")

    if not bullets:
        return ""

    out = "\n".join(bullets)
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return normalize_display_line_breaks(out)


def _user_facing_location_message(lv: dict[str, Any]) -> str | None:
    st = lv.get("status")
    if isinstance(st, str) and st in _LOCATION_MESSAGE_USER_FACING:
        return _LOCATION_MESSAGE_USER_FACING[st]
    msg = lv.get("message")
    if isinstance(msg, str) and msg.strip():
        return sanitize_user_facing_basis_text(msg.strip())
    return None


def fallback_confidence_basis_from_vlm(
    vlm_result: dict[str, Any],
    *,
    has_images: bool = True,
) -> str:
    items: list[dict[str, str]] = []

    summary = vlm_result.get("scene_summary")
    if isinstance(summary, str) and summary.strip():
        items.append(
            {
                "axis": "content",
                "status": "ok",
                "text": sanitize_user_facing_basis_text(summary.strip()),
            },
        )
    elif has_images:
        items.append(
            {
                "axis": "content",
                "status": "ok",
                "text": "글과 사진을 함께 보며 제보 내용을 검토했어요.",
            },
        )

    if has_images:
        lv = vlm_result.get("location_verification")
        if isinstance(lv, dict):
            loc_text = _user_facing_location_message(lv)
            if loc_text:
                st = lv.get("status")
                status = "warn" if st in {"different_area", "unknown"} else "ok"
                items.append({"axis": "location", "status": status, "text": loc_text})

    risk = vlm_result.get("risk_note")
    if isinstance(risk, str) and risk.strip():
        items.append(
            {
                "axis": "caution",
                "status": "warn",
                "text": sanitize_user_facing_basis_text(risk.strip()),
            },
        )

    if not items:
        items.append(
            {
                "axis": "content",
                "status": "ok",
                "text": "제보 내용과 위치 정보를 바탕으로 검토했어요.",
            },
        )

    rendered = render_confidence_basis_markdown(items, has_images=has_images)
    return normalize_display_line_breaks(rendered) if rendered else ""


def resolve_confidence_basis_markdown(
    vlm_result: dict[str, Any],
    *,
    has_images: bool = True,
    max_chars: int = 2000,
) -> str:
    structured = _coerce_basis_items(vlm_result.get("confidence_basis"))
    if structured:
        rendered = render_confidence_basis_markdown(
            structured,
            has_images=has_images,
            max_chars=max_chars,
        )
        if rendered:
            return rendered

    legacy = normalize_confidence_basis_markdown(
        vlm_result.get("confidence_basis_markdown"),
        max_chars=max_chars,
    )
    if legacy:
        return normalize_display_line_breaks(legacy)

    return fallback_confidence_basis_from_vlm(vlm_result, has_images=has_images)


def clamp_confidence_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))
