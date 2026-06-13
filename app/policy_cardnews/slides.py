# 정책 카드뉴스 슬라이드 JSON 파싱·레이아웃

from __future__ import annotations

import json
import re
from typing import Any

from app.policy_cardnews.copy import polish_korean_text

TEMPLATE_LAYOUTS = frozenset({
    "template_cover",
    "template_numbered",
    "template_three_col",
    "template_grid",
    "template_cta",
})

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


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


def _normalize_layout_type(item: dict[str, Any], *, index: int, total: int) -> str:
    layout = str(item.get("layout_type") or "").strip()
    if layout in TEMPLATE_LAYOUTS:
        return layout
    parsed_items = _parse_items(item.get("items"))
    n_items = len(parsed_items)
    if index == 1:
        return "template_cover"
    if index == total:
        return "template_cta"
    if n_items == 3:
        return "template_three_col"
    if n_items == 4:
        return "template_grid"
    return "template_numbered"


def _slide_has_content(item: dict[str, Any]) -> bool:
    if str(item.get("headline") or "").strip():
        return True
    if str(item.get("highlight") or "").strip():
        return True
    if str(item.get("body") or "").strip():
        return True
    if str(item.get("subtext") or "").strip():
        return True
    if str(item.get("cta") or "").strip():
        return True
    return bool(_parse_items(item.get("items")))


def parse_cardnews_slides_json(raw: str) -> list[dict[str, Any]]:
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

    total = len(raw_slides)
    slides: list[dict[str, Any]] = []
    for index, item in enumerate(raw_slides, start=1):
        slides.append(
            {
                "slide": int(item.get("slide") or index),
                "layout_type": _normalize_layout_type(item, index=index, total=total),
                "theme": str(item.get("theme") or "snow_clean").strip(),
                "eyebrow": str(item.get("eyebrow") or "").strip(),
                "headline": str(item.get("headline") or "").strip(),
                "highlight": str(item.get("highlight") or "").strip(),
                "subtext": str(item.get("subtext") or "").strip(),
                "body": str(item.get("body") or "").strip(),
                "items": _parse_items(item.get("items")),
                "cta": polish_korean_text(str(item.get("cta") or "")),
                "speech": polish_korean_text(str(item.get("speech") or "")),
                "emoji": str(item.get("emoji") or "").strip(),
                "use_image": bool(item.get("use_image", True)),
            }
        )

    # 최대 3장까지 사용하되, 첫 장과 마지막 CTA 슬라이드는 항상 보존
    if len(slides) > 3:
        return slides[:2] + [slides[-1]]
    return slides
