from __future__ import annotations

import json
import re
from typing import Any

from app.contest_cardnews.copy import compact_contest_deck
from app.contest_cardnews.template.dispatch import (
    LAYOUT_CHECKLIST,
    LAYOUT_COVER,
    LAYOUT_CTA,
    LAYOUT_TABLE,
    normalize_layout_type,
    pick_middle_layout,
)
from app.contest_cardnews.template.palette import palette_names
from app.policy_cardnews.copy import polish_korean_text

CONTEST_LAYOUTS = frozenset({
    LAYOUT_COVER,
    LAYOUT_TABLE,
    LAYOUT_CHECKLIST,
    LAYOUT_CTA,
})

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")
_MAX_SLIDES = 4


def _parse_items(raw_items: Any) -> list[dict[str, str]]:
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    for item in raw_items:
        if isinstance(item, str):
            text = polish_korean_text(item.strip())
            if text:
                items.append({"label": "", "text": text})
        elif isinstance(item, dict):
            label = polish_korean_text(str(item.get("label") or "").strip())
            text = polish_korean_text(str(item.get("text") or item.get("value") or "").strip())
            if label or text:
                items.append({"label": label, "text": text})
    return items


def _resolve_layout(item: dict[str, Any], *, index: int, total: int) -> str:
    raw = str(item.get("layout_type") or "").strip()
    layout = normalize_layout_type(raw)
    if layout in CONTEST_LAYOUTS:
        return layout
    if index == 1:
        return LAYOUT_COVER
    if index == total:
        return LAYOUT_CTA
    return pick_middle_layout(item)


def _slide_has_content(item: dict[str, Any]) -> bool:
    if str(item.get("headline") or "").strip():
        return True
    if str(item.get("highlight") or "").strip():
        return True
    if str(item.get("body") or "").strip():
        return True
    if str(item.get("eyebrow") or "").strip():
        return True
    if str(item.get("cta") or "").strip():
        return True
    return bool(_parse_items(item.get("items")))


def _resolve_palette(item: dict[str, Any]) -> str:
    raw = str(item.get("template_palette") or "").strip()
    if raw in palette_names():
        return raw
    return ""


def parse_contest_cardnews_slides_json(raw: str) -> list[dict[str, Any]]:
    """공모전 카드뉴스 슬라이드 JSON — layout_type·palette 보존 (정책 파서 사용 금지)."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("카드뉴스 슬라이드 JSON이 비어 있음")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    match = _JSON_ARRAY_RE.search(text)
    if match is None:
        raise ValueError("카드뉴스 슬라이드 JSON 배열을 찾을 수 없음")

    payload = json.loads(match.group(0))
    if not isinstance(payload, list) or not payload:
        raise ValueError("카드뉴스 슬라이드 JSON이 배열이 아님")

    raw_slides = [item for item in payload if isinstance(item, dict) and _slide_has_content(item)]
    if not raw_slides:
        raise ValueError("유효한 카드뉴스 슬라이드가 없음")

    if len(raw_slides) > _MAX_SLIDES:
        raw_slides = [raw_slides[0], *raw_slides[1 : _MAX_SLIDES - 1], raw_slides[-1]]

    raw_slides = compact_contest_deck(
        [{"slide": i + 1, **s} for i, s in enumerate(raw_slides)],
    )

    deck_palette = ""
    for item in raw_slides:
        deck_palette = _resolve_palette(item)
        if deck_palette:
            break

    total = len(raw_slides)
    slides: list[dict[str, Any]] = []
    for index, item in enumerate(raw_slides, start=1):
        layout = _resolve_layout(item, index=index, total=total)
        palette = _resolve_palette(item) or deck_palette
        slides.append(
            {
                "slide": int(item.get("slide") or index),
                "layout_type": layout,
                "template_palette": palette,
                "eyebrow": str(item.get("eyebrow") or "").strip(),
                "headline": str(item.get("headline") or "").strip(),
                "highlight": str(item.get("highlight") or "").strip(),
                "subtext": str(item.get("subtext") or "").strip(),
                "body": str(item.get("body") or "").strip(),
                "items": _parse_items(item.get("items")),
                "cta": polish_korean_text(str(item.get("cta") or "")),
                "speech": polish_korean_text(str(item.get("speech") or "")),
                "point": polish_korean_text(str(item.get("point") or "")),
                "use_image": False,
            },
        )
    return slides
