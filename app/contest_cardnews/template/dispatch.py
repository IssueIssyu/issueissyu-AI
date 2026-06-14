from __future__ import annotations

from typing import Any, Callable

from PIL import Image

from app.contest_cardnews.template.base import ContestRenderContext
from app.contest_cardnews.template.layouts import (
    render_contest_body,
    render_contest_checklist,
    render_contest_cover,
    render_contest_cta,
    render_contest_headline,
    render_contest_table,
    render_contest_three_col,
)
from app.contest_cardnews.template.palette import ContestPalette, resolve_palette

LAYOUT_COVER = "contest_cover"
LAYOUT_HEADLINE = "contest_headline"
LAYOUT_BODY = "contest_body"
LAYOUT_TABLE = "contest_table"
LAYOUT_CHECKLIST = "contest_checklist"
LAYOUT_THREE_COL = "contest_three_col"
LAYOUT_CTA = "contest_cta"

# 캐릭터는 표지·CTA만 (중간 슬라이드와 겹침 방지)
MASCOT_LAYOUTS = {LAYOUT_COVER, LAYOUT_CTA}

_LEGACY_LAYOUT_MAP = {
    "template_cover": LAYOUT_COVER,
    "template_numbered": LAYOUT_CHECKLIST,
    "template_grid": LAYOUT_TABLE,
    "template_three_col": LAYOUT_THREE_COL,
    "template_cta": LAYOUT_CTA,
}

_RENDERERS: dict[str, Callable[[ContestRenderContext], Image.Image]] = {
    LAYOUT_COVER: render_contest_cover,
    LAYOUT_HEADLINE: render_contest_headline,
    LAYOUT_BODY: render_contest_body,
    LAYOUT_TABLE: render_contest_table,
    LAYOUT_CHECKLIST: render_contest_checklist,
    LAYOUT_THREE_COL: render_contest_three_col,
    LAYOUT_CTA: render_contest_cta,
}


def normalize_layout_type(raw: str) -> str:
    key = (raw or "").strip()
    if key in _RENDERERS:
        return key
    return _LEGACY_LAYOUT_MAP.get(key, key)


def pick_middle_layout(slide: dict[str, Any]) -> str:
    items = [
        i
        for i in list(slide.get("items") or [])
        if str(i.get("text") or "").strip()
    ]
    n = len(items)
    if n == 3:
        return LAYOUT_THREE_COL
    if n >= 4:
        return LAYOUT_TABLE
    if n >= 1:
        return LAYOUT_CHECKLIST
    body = str(slide.get("body") or "").strip()
    if len(body) > 80:
        return LAYOUT_BODY
    return LAYOUT_HEADLINE


def normalize_contest_slide(slide: dict[str, Any], *, index: int, total: int) -> dict[str, Any]:
    row = dict(slide)
    layout = normalize_layout_type(str(row.get("layout_type") or ""))
    if not layout or layout not in _RENDERERS:
        if index == 1:
            layout = LAYOUT_COVER
        elif index == total:
            layout = LAYOUT_CTA
        else:
            layout = pick_middle_layout(row)
    row["layout_type"] = layout
    return row


def render_contest_slide(
    slide: dict[str, Any],
    *,
    palette: ContestPalette | None = None,
    mascot: Image.Image | None = None,
    source_url: str = "",
) -> Image.Image:
    pal = palette or resolve_palette(str(slide.get("template_palette") or "pastel_mint"))
    layout = normalize_layout_type(str(slide.get("layout_type") or LAYOUT_COVER))
    renderer = _RENDERERS.get(layout, render_contest_headline)
    url = (source_url or str(slide.get("source_url") or "")).strip()
    ctx = ContestRenderContext(
        slide=slide,
        palette=pal,
        mascot=mascot,
        source_url=url,
    )
    return renderer(ctx)
