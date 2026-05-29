from __future__ import annotations

from typing import Any

from app.contest_cardnews.template.dispatch import (
    LAYOUT_CHECKLIST,
    LAYOUT_COVER,
    LAYOUT_CTA,
    LAYOUT_TABLE,
    normalize_layout_type,
)
from app.policy_cardnews.copy import is_filler_text, polish_korean_text

_SPEECH_MAX = 14
_TARGET_SLIDES = 3
_MIDDLE_LAYOUTS = (LAYOUT_TABLE, LAYOUT_CHECKLIST)


def _content_score(slide: dict[str, Any]) -> int:
    score = 0
    for key in ("eyebrow", "headline", "highlight", "body", "cta", "point"):
        score += len(str(slide.get(key) or "").strip())
    for item in slide.get("items") or []:
        if isinstance(item, dict):
            score += len(str(item.get("label") or "")) + len(str(item.get("text") or ""))
    return score


def _middle_layout_bonus(layout: str) -> int:
    if layout == LAYOUT_TABLE:
        return 40
    if layout == LAYOUT_CHECKLIST:
        return 30
    return 0


def compact_contest_deck(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """표지 + 요약 1장 + CTA = 3장. 중간은 table/checklist 우선."""
    rows = [s for s in slides if isinstance(s, dict)]
    if len(rows) <= _TARGET_SLIDES:
        return _renumber_slides(rows)

    cover = rows[0]
    cta = rows[-1]
    middles = rows[1:-1]

    def rank(slide: dict[str, Any]) -> tuple[int, int]:
        layout = normalize_layout_type(str(slide.get("layout_type") or ""))
        prefer = 0 if layout in _MIDDLE_LAYOUTS else 1
        return (prefer, -(_content_score(slide) + _middle_layout_bonus(layout)))

    best_middle = min(middles, key=rank)
    merged_layout = normalize_layout_type(str(best_middle.get("layout_type") or ""))
    if merged_layout not in _MIDDLE_LAYOUTS:
        if len(best_middle.get("items") or []) >= 3:
            best_middle = {**best_middle, "layout_type": LAYOUT_CHECKLIST}
        elif best_middle.get("items"):
            best_middle = {**best_middle, "layout_type": LAYOUT_TABLE}

    return _renumber_slides([cover, best_middle, cta])


def _renumber_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, slide in enumerate(slides, start=1):
        row = dict(slide)
        row["slide"] = index
        out.append(row)
    return out


def normalize_contest_slide_copy(slide: dict[str, Any]) -> dict[str, Any]:
    row = dict(slide)
    layout = str(row.get("layout_type") or "").strip()

    for key in ("eyebrow", "headline", "highlight", "subtext", "body", "cta", "speech", "point"):
        if key in row:
            row[key] = polish_korean_text(str(row.get(key) or ""))

    simplified_items: list[dict[str, str]] = []
    for item in row.get("items") or []:
        if isinstance(item, dict):
            simplified_items.append(
                {
                    "label": polish_korean_text(str(item.get("label") or item.get("title") or "")),
                    "text": polish_korean_text(
                        str(item.get("text") or item.get("value") or item.get("content") or ""),
                    ),
                },
            )
        elif str(item).strip():
            simplified_items.append({"label": "", "text": polish_korean_text(str(item))})
    if simplified_items:
        row["items"] = simplified_items[:5]

    headline = row.get("headline", "")
    highlight = row.get("highlight", "")
    if highlight and headline and highlight == headline and "cover" in layout:
        row["headline"] = ""

    body = row.get("body", "")
    if body and is_filler_text(body) and "cover" not in layout:
        row["body"] = ""

    if not row.get("speech"):
        row["speech"] = _derive_contest_speech(row, layout=layout)

    row["use_image"] = False
    return row


def _derive_contest_speech(slide: dict[str, Any], *, layout: str) -> str:
    explicit = str(slide.get("speech") or "").strip()
    if explicit and len(explicit) <= _SPEECH_MAX:
        return explicit
    if "cta" in layout:
        cta = str(slide.get("cta") or "").strip()
        if cta and len(cta) <= _SPEECH_MAX:
            return cta.rstrip(".!") + "!"
    if "cover" in layout:
        return "놓치지 마!"
    return ""


def is_contest_slide_empty(slide: dict[str, Any]) -> bool:
    layout = str(slide.get("layout_type") or "")
    if "cover" in layout:
        return not bool(
            str(slide.get("headline") or "").strip()
            or str(slide.get("highlight") or "").strip()
            or str(slide.get("body") or "").strip()
            or str(slide.get("eyebrow") or "").strip()
        )
    if "cta" in layout:
        return not (
            bool(str(slide.get("cta") or "").strip())
            or bool(str(slide.get("headline") or "").strip())
        )
    if slide.get("items"):
        return len([i for i in slide["items"] if str(i.get("text") or "").strip()]) == 0
    return not bool(str(slide.get("body") or slide.get("headline") or "").strip())


def prepare_contest_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = compact_contest_deck(slides)
    return [normalize_contest_slide_copy(s) for s in rows if not is_contest_slide_empty(s)]
