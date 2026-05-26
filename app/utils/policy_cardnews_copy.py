from __future__ import annotations

import re
from typing import Any

from app.utils.policy_cardnews_terms import simplify_policy_text

# LLM이 자주 쓰는 의미 없는 채움 문구
_FILLER_PATTERNS = (
    r"정책\s*현장\s*사진",
    r"한눈에\s*보기",
    r"핵심만\s*정리",
    r"확인해\s*보세요\.?$",
    r"확인하세요\.?$",
    r"더\s*자세히\s*알아보",
)

_FILLER_RE = re.compile("|".join(f"(?:{p})" for p in _FILLER_PATTERNS), re.IGNORECASE)

_SPELLING_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"되요\b"), "돼요"),
    (re.compile(r"안되요"), "안 돼요"),
    (re.compile(r"안돼요"), "안 돼요"),
    (re.compile(r"확인해주세요"), "확인해 주세요"),
    (re.compile(r"신청해주세요"), "신청해 주세요"),
    (re.compile(r"알려주세요"), "알려 주세요"),
    (re.compile(r"해보세요"), "해 보세요"),
    (re.compile(r"해당되는지"), "해당하는지"),
    (re.compile(r"\s{2,}"), " "),
)


def polish_korean_text(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    for pattern, replacement in _SPELLING_FIXES:
        value = pattern.sub(replacement, value)
    return value.strip()


def is_filler_text(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return True
    if len(value) < 6 and value.endswith(("!", "?", ".")):
        return False
    return bool(_FILLER_RE.search(value))


def normalize_slide_copy(slide: dict[str, Any]) -> dict[str, Any]:
    row = dict(slide)
    layout = str(row.get("layout_type") or "cover_big_typo")

    for key in ("eyebrow", "headline", "highlight", "subtext", "body", "cta", "speech"):
        row[key] = simplify_policy_text(polish_korean_text(str(row.get(key) or "")))

    simplified_items: list[dict[str, str]] = []
    for item in row.get("items") or []:
        if isinstance(item, dict):
            simplified_items.append(
                {
                    "label": simplify_policy_text(polish_korean_text(str(item.get("label") or ""))),
                    "text": simplify_policy_text(polish_korean_text(str(item.get("text") or ""))),
                }
            )
        elif str(item).strip():
            simplified_items.append({"label": "", "text": simplify_policy_text(polish_korean_text(str(item)))})
    if simplified_items:
        row["items"] = simplified_items

    highlight = row["highlight"]
    headline = row["headline"]
    body = row["body"]
    subtext = row["subtext"]
    speech = row["speech"]

    if highlight and headline and highlight == headline:
        if layout == "cover_big_typo":
            headline = ""
        else:
            highlight = ""

    if body and is_filler_text(body):
        body = ""
    if subtext and is_filler_text(subtext):
        subtext = ""
    if headline and is_filler_text(headline) and layout != "cover_big_typo":
        headline = ""

    if not body and subtext:
        body = subtext
        subtext = ""

    if not headline and highlight and layout != "cover_big_typo":
        headline = highlight
        highlight = ""

    if not speech:
        speech = derive_speech(row, layout=layout)

    row["highlight"] = highlight
    row["headline"] = headline
    row["body"] = body
    row["subtext"] = subtext
    row["speech"] = speech
    return row


def derive_speech(slide: dict[str, Any], *, layout: str) -> str:
    explicit = polish_korean_text(str(slide.get("speech") or ""))
    if explicit:
        return explicit[:18]

    if layout in {"cta", "template_cta"}:
        cta = polish_korean_text(str(slide.get("cta") or ""))
        if cta:
            return f"{cta}!"[:18]

    for candidate in (
        slide.get("highlight"),
        slide.get("headline"),
        slide.get("body"),
    ):
        text = polish_korean_text(str(candidate or ""))
        if text and not is_filler_text(text) and len(text) <= 18:
            if layout in {"cover_big_typo", "template_cover", "cta", "template_cta"}:
                return f"{text.rstrip('.!')}!"[:18]

    if layout in {"cover_big_typo", "template_cover"}:
        return "이거 꼭 봐!"
    if layout in {"cta", "template_cta"}:
        return "원문 확인해!"
    return ""


def slide_content_score(slide: dict[str, Any]) -> int:
    score = 0
    for key in ("eyebrow", "headline", "highlight", "subtext", "body", "cta", "speech"):
        score += len(str(slide.get(key) or "").strip())
    for item in slide.get("items") or []:
        if isinstance(item, dict):
            score += len(str(item.get("label") or "")) + len(str(item.get("text") or ""))
        else:
            score += len(str(item).strip())
    return score


def _merge_slides(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    merged = dict(target)
    merged_items = list(merged.get("items") or [])
    seen = {str(i.get("text") if isinstance(i, dict) else i).strip() for i in merged_items}

    for item in source.get("items") or []:
        text = str(item.get("text") if isinstance(item, dict) else item).strip()
        if text and text not in seen:
            merged_items.append(item if isinstance(item, dict) else {"label": "", "text": text})
            seen.add(text)
    merged["items"] = merged_items[:8]

    for field in ("body", "headline", "highlight", "subtext"):
        if not str(merged.get(field) or "").strip():
            value = str(source.get(field) or "").strip()
            if value and not is_filler_text(value):
                merged[field] = value

    if len(merged.get("items") or []) >= 2:
        merged["layout_type"] = "info_blocks"
    merged["speech"] = ""
    return merged


def compact_cardnews_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # 여백 많은 중간 슬라이드는 이전 장에 병합하거나 제외
    if not slides:
        return []

    working = [dict(s) for s in slides[:3]]
    working[0]["layout_type"] = "cover_big_typo"
    if len(working) > 1:
        working[-1]["layout_type"] = "cta"
    # 템플릿 모드에서는 렌더 단계에서 layout 재매핑

    merged: list[dict[str, Any]] = []
    min_middle_score = 45

    for slide in working:
        layout = str(slide.get("layout_type") or "")
        score = slide_content_score(slide)

        if layout in {"cover_big_typo", "cta"}:
            merged.append(slide)
            continue

        if score < 20:
            continue
        if score < min_middle_score and merged:
            merged[-1] = _merge_slides(merged[-1], slide)
            continue
        merged.append(slide)

    if len(merged) == 1 and len(working) > 1 and str(working[-1].get("layout_type")) == "cta":
        merged.append(working[-1])

    result: list[dict[str, Any]] = []
    for index, slide in enumerate(merged[:3], start=1):
        row = dict(slide)
        row["slide"] = index
        result.append(row)
    return result


def is_slide_empty(slide: dict[str, Any]) -> bool:
    layout = str(slide.get("layout_type") or "")
    score = slide_content_score(slide)
    if layout in {"cover_big_typo", "template_cover"}:
        return not bool(
            str(slide.get("headline") or "").strip()
            or str(slide.get("highlight") or "").strip()
            or str(slide.get("body") or "").strip()
        )
    if layout in {"cta", "template_cta"}:
        return not (
            bool(str(slide.get("cta") or "").strip()) or bool(str(slide.get("headline") or "").strip())
        )
    if layout in {"info_blocks", "template_numbered", "template_three_col", "template_grid"}:
        return score < 50 and len(slide.get("items") or []) < 3
    return score < 40
