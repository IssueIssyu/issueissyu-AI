# JSON 기반 정책 카드뉴스 템플릿 렌더러

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.policy_cardnews.constants import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CONTENT_PAD,
    GAP_BLOCK,
    GAP_LINE_LG,
    GAP_LINE_MD,
    GAP_LINE_SM,
    GAP_SECTION,
)
from app.policy_cardnews.mascot import BRAND_ACCENT
from app.policy_cardnews.template.draw import (
    draw_cta_action_panel,
    draw_frame_base,
    draw_highlighter_title,
    draw_template_header,
    fill_scale,
    fit_font_lines,
    line_height,
    measure_text_block,
    scaled_size,
    wrap_text,
)
from app.policy_cardnews.template.metrics import COVER_TEXT_RATIO_WITH_HERO
from app.policy_cardnews.visual import paste_rounded_image_cover, paste_rounded_image_fit

_REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = _REPO_ROOT / "app" / "assets" / "policy_cardnews_templates"

INK = (20, 24, 32)
INK_BODY = (52, 60, 78)
GRAY_PANEL = (244, 246, 250)
DOT_GRAY = (200, 208, 220)
INSET_PANEL = 22
GAP_COL = 20
GAP_TILE = 18
GAP_ROW = 14
INSET_TILE = 24

_TEMPLATE_CACHE: dict[Path, dict[str, Any]] = {}


def load_template_config(name: str) -> dict[str, Any]:
    path = TEMPLATE_DIR / f"{name}.json"
    cached = _TEMPLATE_CACHE.get(path)
    if cached is not None:
        return cached
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"template json must be object: {path}")
    _TEMPLATE_CACHE[path] = payload
    return payload


def _slide_items(slide: dict[str, Any]) -> list[dict[str, str]]:
    items = [i for i in list(slide.get("items") or []) if str(i.get("text") or "").strip()]
    if not items and slide.get("body"):
        items = [{"label": "", "text": t} for t in str(slide["body"]).split("\n") if t.strip()]
    return items[:6]


def _center_block_x(block_w: int, cx0: int, cx1: int) -> int:
    return cx0 + max(0, (cx1 - cx0 - block_w) // 2)


def _fit_text_in_rect(
    draw: ImageDraw.ImageDraw,
    text: str,
    inner_w: int,
    inner_h: int,
    *,
    start_size: int,
    min_size: int,
    line_gap: int,
    load_font_fn: Any,
    bold: bool = False,
    extra_bold: bool = False,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    value = (text or "").strip()
    if not value or inner_h < 16 or inner_w < 32:
        return load_font_fn(min_size, bold=bold, extra_bold=extra_bold), []

    for size in range(start_size, min_size - 1, -2):
        font = load_font_fn(size, bold=bold, extra_bold=extra_bold)
        lines = wrap_text(draw, value, font, inner_w)
        lh = line_height(font, line_gap)
        max_lines = max(1, inner_h // max(lh, 1))
        clipped = lines[:max_lines]
        if len(lines) <= max_lines:
            block_h = measure_text_block(clipped, font, line_gap=line_gap)
            if block_h <= inner_h:
                return font, clipped

    font = load_font_fn(min_size, bold=bold, extra_bold=extra_bold)
    lines = wrap_text(draw, value, font, inner_w)
    lh = line_height(font, line_gap)
    max_lines = max(1, inner_h // max(lh, 1))
    return font, lines[:max_lines]


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    *,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    x0: int,
    width: int,
    y: int,
    fill: tuple[int, int, int],
    line_gap: int,
) -> int:
    cy = y
    for line in lines:
        lw = int(draw.textlength(line, font=font))
        draw.text((x0 + (width - lw) // 2, cy), line, font=font, fill=fill)
        cy += line_height(font, line_gap)
    return cy


def _new_canvas(ctx: Any, config_name: str) -> tuple[Any, Image.Image, ImageDraw.ImageDraw, Any, int, int, int, int, int]:
    from types import SimpleNamespace

    config = load_template_config(config_name)
    palette = ctx.palette
    frame_cfg = config.get("frame") or {}
    card_inset = int(frame_cfg.get("card_inset", 36))
    content_pad = int(frame_cfg.get("content_pad", CONTENT_PAD))
    offset_px = int(frame_cfg.get("offset_px", 12))
    white, content = _card_frame(card_inset=card_inset, content_pad=content_pad)
    cx0, cy0, cx1, cy1 = content
    frame = SimpleNamespace(white=white, content=content)
    canvas = draw_frame_base(
        canvas_width=CANVAS_WIDTH,
        canvas_height=CANVAS_HEIGHT,
        outer_fill=tuple(palette.outer),
        offset_fill=tuple(palette.offset),
        white_rect=white,
        offset_px=offset_px,
    )
    draw = ImageDraw.Draw(canvas)
    return config, canvas, draw, frame, cx0, cy0, cx1, cy1, cx1 - cx0


def _draw_slide_header(
    draw: ImageDraw.ImageDraw,
    *,
    frame: Any,
    palette: Any,
    eyebrow: str,
    headline: str,
    bottom_limit: int,
    load_font_fn: Any,
) -> int:
    def _highlighter(draw_obj: ImageDraw.ImageDraw, **kwargs: Any) -> int:
        return _draw_header_highlighter(draw_obj, **kwargs)

    return draw_template_header(
        draw,
        frame=frame,
        palette=palette,
        eyebrow=eyebrow,
        headline=headline,
        bottom_limit=bottom_limit,
        fit_font_lines_fn=lambda d, t, mw, **kw: fit_font_lines(d, t, mw, load_font_fn=load_font_fn, **kw),
        line_height_fn=line_height,
        draw_highlighter_title_fn=_highlighter,
        fill_scale_fn=fill_scale,
        scaled_size_fn=scaled_size,
        gap_block=GAP_BLOCK,
        gap_line_md=GAP_LINE_MD,
        gap_line_lg=GAP_LINE_LG,
        gap_section=GAP_SECTION,
    )


def _card_frame(*, card_inset: int, content_pad: int) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    wx0 = card_inset
    wy0 = card_inset
    wx1 = CANVAS_WIDTH - card_inset
    wy1 = CANVAS_HEIGHT - card_inset
    white = (wx0, wy0, wx1, wy1)
    content = (wx0 + content_pad, wy0 + content_pad, wx1 - content_pad, wy1 - content_pad)
    return white, content


def _fonts_cfg(config: dict[str, Any]) -> dict[str, int]:
    fonts = config.get("fonts") or {}
    return {
        "eyebrow_start": int(fonts.get("eyebrow_start", 34)),
        "eyebrow_min": int(fonts.get("eyebrow_min", 26)),
        "eyebrow_max_lines": int(fonts.get("eyebrow_max_lines", 2)),
        "headline_start": int(fonts.get("headline_start", 80)),
        "headline_min": int(fonts.get("headline_min", 52)),
        "headline_max_lines": int(fonts.get("headline_max_lines", 2)),
        "highlight_start": int(fonts.get("highlight_start", 76)),
        "highlight_min": int(fonts.get("highlight_min", 48)),
        "highlight_max_lines": int(fonts.get("highlight_max_lines", 2)),
    }


def _highlight_cfg(config: dict[str, Any]) -> dict[str, Any]:
    hl = config.get("highlight") or {}
    layout = config.get("layout") or {}
    text_fill_raw = hl.get("text_fill")
    if isinstance(text_fill_raw, (list, tuple)) and len(text_fill_raw) == 3:
        text_fill = tuple(int(v) for v in text_fill_raw)
    else:
        text_fill = INK
    return {
        "type": str(hl.get("type", "accent_badge")),
        "radius": int(hl.get("radius", layout.get("highlight_badge_radius", 8))),
        "pad_x": int(hl.get("pad_x", layout.get("highlight_badge_pad_x", 18))),
        "pad_y": int(hl.get("pad_y", layout.get("highlight_badge_pad_y", 5))),
        "tape_extra_h": int(hl.get("tape_extra_h", 14)),
        "line_gap": int(hl.get("line_gap", GAP_LINE_MD)),
        "text_fill": text_fill,
    }


def _draw_highlight_accent_badge(
    draw: ImageDraw.ImageDraw,
    *,
    cx: int,
    y: int,
    line: str,
    font: ImageFont.FreeTypeFont,
    accent_fill: tuple[int, int, int],
    text_fill: tuple[int, int, int] = INK,
    radius: int,
    pad_x: int,
    pad_y: int,
    tape_extra_h: int,
) -> int:
    lw = int(draw.textlength(line, font=font))
    tape_h = line_height(font, 6) + tape_extra_h
    draw.rounded_rectangle(
        (cx - lw // 2 - pad_x, y, cx + lw // 2 + pad_x, y + tape_h),
        radius=radius,
        fill=accent_fill,
    )
    draw.text((cx - lw // 2, y + pad_y), line, font=font, fill=text_fill)
    return y + tape_h + GAP_LINE_LG


def render_template_cover(ctx: Any) -> Image.Image:
    """`template_cover.json` 기반 표지 슬라이드."""
    from app.policy_cardnews.template.dispatch import (
        _load_font,
        _paste_mascot_zone,
    )

    config = load_template_config("template_cover")
    slide = ctx.slide
    palette = ctx.palette

    frame_cfg = config.get("frame") or {}
    card_inset = int(frame_cfg.get("card_inset", 36))
    content_pad = int(frame_cfg.get("content_pad", CONTENT_PAD))
    offset_px = int(frame_cfg.get("offset_px", 12))

    white, content = _card_frame(card_inset=card_inset, content_pad=content_pad)
    cx0, cy0, cx1, cy1 = content
    cw = cx1 - cx0
    cx = (cx0 + cx1) // 2

    layout_cfg = config.get("layout") or {}
    cover_text_ratio_with_hero = float(
        layout_cfg.get("text_bottom_ratio_with_hero", COVER_TEXT_RATIO_WITH_HERO)
    )
    fonts = _fonts_cfg(config)
    highlight_cfg = _highlight_cfg(config)

    canvas = draw_frame_base(
        canvas_width=CANVAS_WIDTH,
        canvas_height=CANVAS_HEIGHT,
        outer_fill=tuple(palette.outer),
        offset_fill=tuple(palette.offset),
        white_rect=white,
        offset_px=offset_px,
    )
    draw = ImageDraw.Draw(canvas)

    eyebrow = str(slide.get("eyebrow") or slide.get("subtext") or "").strip()
    headline = str(slide.get("headline") or "").strip()
    highlight = str(slide.get("highlight") or "").strip()
    speech = str(slide.get("speech") or "").strip()

    hero_cfg = config.get("hero") or {}
    hero_enabled = bool(hero_cfg.get("enabled", True))
    use_hero_image = bool(
        hero_enabled and ctx.use_cover_image and ctx.hero_image is not None
    )
    use_mascot_hero = bool(not use_hero_image and ctx.mascot is not None)
    use_visual_fill = use_hero_image or use_mascot_hero

    if use_visual_fill:
        text_bottom = cy0 + int((cy1 - cy0) * cover_text_ratio_with_hero)
    else:
        text_bottom = cy1 - content_pad // 2

    text_available = text_bottom - cy0
    parts: list[tuple[str, str]] = []
    if eyebrow:
        parts.append(("eyebrow", eyebrow))
    if headline:
        parts.append(("headline", headline))
    if highlight and highlight != headline:
        parts.append(("highlight", highlight))

    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    def _fit_block(kind: str, text: str, scale: float) -> tuple[Any, list[str], int]:
        if kind == "eyebrow":
            max_lines = fonts["eyebrow_max_lines"]
            font, lines = fit_font_lines(
                probe,
                text,
                cw - 32,
                start_size=scaled_size(fonts["eyebrow_start"], scale),
                min_size=fonts["eyebrow_min"],
                max_lines=max_lines,
                load_font_fn=_load_font,
                bold=True,
            )
            block_h = measure_text_block(lines, font, line_gap=GAP_LINE_SM) + GAP_LINE_LG
            return font, lines, block_h
        if kind == "headline":
            max_lines = fonts["headline_max_lines"]
            font, lines = fit_font_lines(
                probe,
                text,
                cw - 40,
                start_size=scaled_size(fonts["headline_start"], scale),
                min_size=fonts["headline_min"],
                max_lines=max_lines,
                load_font_fn=_load_font,
                extra_bold=True,
            )
            block_h = measure_text_block(lines, font, line_gap=GAP_LINE_MD) + GAP_LINE_LG
            return font, lines, block_h
        max_lines = fonts["highlight_max_lines"]
        font, lines = fit_font_lines(
            probe,
            text,
            cw - 40,
            start_size=scaled_size(fonts["highlight_start"], scale),
            min_size=fonts["highlight_min"],
            max_lines=max_lines,
            load_font_fn=_load_font,
            extra_bold=True,
        )
        tape_h = line_height(font, 6) + highlight_cfg["tape_extra_h"]
        block_h = len(lines) * (tape_h + GAP_LINE_LG) if lines else 0
        return font, lines, block_h

    scale = fill_scale(1, text_available, max_scale=1.78)
    blocks: list[tuple[str, str, Any, list[str], int]] = []
    for _ in range(28):
        total = GAP_BLOCK
        blocks = []
        for kind, text in parts:
            font, lines, block_h = _fit_block(kind, text, scale)
            blocks.append((kind, text, font, lines, block_h))
            total += block_h
        if total <= text_available:
            break
        scale = max(1.0, scale * (text_available / total) * 0.96)

    y = cy0 + max(GAP_BLOCK, int((text_available - total) * 0.08))

    for kind, text, font, lines, block_h in blocks:
        if kind == "eyebrow":
            for line in lines:
                lh = line_height(font, GAP_LINE_SM)
                lw = int(draw.textlength(line, font=font))
                draw.text((cx - lw // 2, y), line, font=font, fill=INK_BODY)
                y += lh
            y += GAP_LINE_LG
        elif kind == "headline":
            for line in lines:
                lh = line_height(font, GAP_LINE_MD)
                lw = int(draw.textlength(line, font=font))
                draw.text((cx - lw // 2, y), line, font=font, fill=INK)
                y += lh
            y += GAP_LINE_LG
        else:
            for line in lines:
                if highlight_cfg["type"] == "highlight_bar":
                    y = draw_highlighter_title(
                        draw,
                        x=cx0,
                        y=y,
                        text=line,
                        max_w=cw,
                        font=font,
                        highlight_fill=tuple(palette.offset),
                        text_fill=INK,
                        wrap_fn=wrap_text,
                        line_height_fn=line_height,
                        line_gap=highlight_cfg["line_gap"],
                    )
                    y += GAP_LINE_LG
                else:
                    y = _draw_highlight_accent_badge(
                        draw,
                        cx=cx,
                        y=y,
                        line=line,
                        font=font,
                        accent_fill=tuple(palette.offset),
                        text_fill=highlight_cfg["text_fill"],
                        radius=highlight_cfg["radius"],
                        pad_x=highlight_cfg["pad_x"],
                        pad_y=highlight_cfg["pad_y"],
                        tape_extra_h=highlight_cfg["tape_extra_h"],
                    )

    img_y0 = y + GAP_SECTION
    img_y1 = cy1 - content_pad // 2

    if use_hero_image and ctx.hero_image is not None:
        radius = int(hero_cfg.get("corner_radius", 28))
        box_inset = int(hero_cfg.get("box_inset", INSET_PANEL))
        img_box = (cx0 + box_inset, img_y0, cx1 - box_inset, img_y1)
        fill_mode = str(hero_cfg.get("fill_mode") or "contain").strip().lower()
        if fill_mode == "cover":
            canvas = paste_rounded_image_cover(canvas, ctx.hero_image, box=img_box, radius=radius)
        else:
            canvas = paste_rounded_image_fit(canvas, ctx.hero_image, box=img_box, radius=radius)
        return canvas.convert("RGB")

    if use_mascot_hero and ctx.mascot is not None:
        return _paste_mascot_zone(
            canvas,
            ctx.mascot,
            speech,
            zone_top=img_y0,
            zone_bottom=img_y1,
            align="center",
        )
    return canvas.convert("RGB")


def _draw_header_highlighter(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    text: str,
    max_w: int,
    font: ImageFont.FreeTypeFont,
    highlight_fill: tuple[int, int, int],
    line_gap: int,
) -> int:
    return draw_highlighter_title(
        draw,
        x=x,
        y=y,
        text=text,
        max_w=max_w,
        font=font,
        highlight_fill=highlight_fill,
        text_fill=INK,
        wrap_fn=wrap_text,
        line_height_fn=line_height,
        line_gap=line_gap,
    )


def _draw_term_guide_panel(
    draw: ImageDraw.ImageDraw,
    *,
    cx0: int,
    cx1: int,
    y: int,
    guides: list[str],
    bottom_limit: int,
    panel_inset: int,
    title: str,
    title_size: int,
    body_size: int,
    panel_radius: int,
    max_guides: int,
    max_body_lines: int,
    load_font_fn: Any,
) -> int:
    lines = [g.strip() for g in guides if g.strip()][:max_guides]
    if not lines or y >= bottom_limit - 60:
        return y

    pad_x = panel_inset
    inner_w = cx1 - cx0 - pad_x * 2
    title_f = load_font_fn(title_size, bold=True)
    body_f = load_font_fn(body_size)
    title_h = line_height(title_f, GAP_LINE_SM)
    body_lines: list[str] = []
    for line in lines:
        body_lines.extend(wrap_text(draw, line, body_f, inner_w)[:2])
    body_lines = body_lines[:max_body_lines]
    panel_h = (
        pad_x
        + title_h
        + GAP_LINE_SM
        + measure_text_block(body_lines, body_f, line_gap=GAP_LINE_SM)
        + pad_x
    )
    panel_h = min(panel_h, max(80, bottom_limit - y - GAP_BLOCK))
    px0 = cx0 + pad_x
    px1 = cx1 - pad_x
    py0 = y
    py1 = min(bottom_limit - GAP_BLOCK, py0 + panel_h)
    draw.rounded_rectangle((px0, py0, px1, py1), radius=panel_radius, fill=GRAY_PANEL)
    ty = py0 + pad_x // 2
    draw.text((px0 + pad_x, ty), title, font=title_f, fill=INK)
    ty += title_h + GAP_LINE_SM
    for line in body_lines:
        draw.text((px0 + pad_x, ty), line, font=body_f, fill=INK_BODY)
        ty += line_height(body_f, GAP_LINE_SM)
    return py1 + GAP_SECTION


def render_template_cta(ctx: Any) -> Image.Image:
    """`template_cta.json` 기반 마무리(CTA) 슬라이드."""
    from types import SimpleNamespace

    from app.policy_cardnews.template.dispatch import (
        _estimate_cta_mascot_zone_height,
        _load_font,
        _paste_mascot_zone,
    )

    config = load_template_config("template_cta")
    slide = ctx.slide
    palette = ctx.palette
    defaults = config.get("defaults") or {}
    layout_cfg = config.get("layout") or {}
    fonts_cfg = config.get("fonts") or {}
    panel_cfg = config.get("cta_panel") or {}
    url_cfg = config.get("url") or {}
    term_cfg = config.get("term_guide") or {}

    frame_cfg = config.get("frame") or {}
    card_inset = int(frame_cfg.get("card_inset", 36))
    content_pad = int(frame_cfg.get("content_pad", CONTENT_PAD))
    offset_px = int(frame_cfg.get("offset_px", 12))
    panel_inset = int(layout_cfg.get("panel_inset", INSET_PANEL))
    gap_above_mascot = int(layout_cfg.get("gap_above_mascot", 36))

    white, content = _card_frame(card_inset=card_inset, content_pad=content_pad)
    cx0, cy0, cx1, cy1 = content
    cw = cx1 - cx0
    frame = SimpleNamespace(white=white, content=content)

    canvas = draw_frame_base(
        canvas_width=CANVAS_WIDTH,
        canvas_height=CANVAS_HEIGHT,
        outer_fill=tuple(palette.outer),
        offset_fill=tuple(palette.offset),
        white_rect=white,
        offset_px=offset_px,
    )
    draw = ImageDraw.Draw(canvas)

    eyebrow = str(slide.get("eyebrow") or defaults.get("eyebrow", "마무리")).strip()
    headline = str(slide.get("headline") or defaults.get("headline", "자세한 내용은 원문에서")).strip()
    cta = str(slide.get("cta") or defaults.get("cta", "원문 뉴스 보기")).strip()
    body = str(slide.get("body") or "").strip()
    speech = str(slide.get("speech") or "").strip()
    speech_max = int(defaults.get("speech_max_len", 18))
    if not speech:
        speech = str(defaults.get("speech", "궁금하면 원문 봐!")).strip()
    speech = speech[:speech_max]
    term_guides = [str(g).strip() for g in list(slide.get("term_guides") or []) if str(g).strip()]

    has_mascot = ctx.mascot is not None
    mascot_bottom = cy1 - content_pad // 2
    mascot_top = mascot_bottom
    content_limit = mascot_bottom

    if has_mascot and ctx.mascot is not None:
        zone_h = _estimate_cta_mascot_zone_height(
            ctx.mascot,
            speech,
            cx0=cx0,
            cx1=cx1,
            zone_bottom=mascot_bottom,
            zone_top_limit=cy0,
        )
        mascot_top = mascot_bottom - zone_h
        content_limit = mascot_top - gap_above_mascot

    available = max(120, content_limit - cy0)
    scale = fill_scale(
        int(layout_cfg.get("content_scale_base", 180)),
        available,
        min_scale=float(layout_cfg.get("content_scale_min", 1.08)),
        max_scale=float(layout_cfg.get("content_scale_max", 1.48)),
    )

    panel_x0 = cx0 + panel_inset
    panel_x1 = cx1 - panel_inset
    box_h = scaled_size(
        int(panel_cfg.get("height_start", 96)),
        scale,
        min_size=int(panel_cfg.get("height_min", 76)),
        max_size=int(panel_cfg.get("height_max", 108)),
    )
    uf = _load_font(
        scaled_size(int(fonts_cfg.get("url_start", 20)), scale, min_size=int(fonts_cfg.get("url_min", 18)))
    )
    url_line_h = line_height(uf, GAP_LINE_SM)
    url = (ctx.source_url or "").strip()
    url_block_h = url_line_h + (GAP_LINE_LG if url else 0)

    term_block_h = 0
    if term_guides:
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        tf = _load_font(int(fonts_cfg.get("term_title", 22)), bold=True)
        bf = _load_font(int(fonts_cfg.get("term_body", 20)))
        for g in term_guides[: int(term_cfg.get("max_guides", 2))]:
            term_block_h += line_height(tf, GAP_LINE_SM) + measure_text_block(
                wrap_text(probe, g, bf, cw - panel_inset * 4)[:2], bf, line_gap=GAP_LINE_SM
            )
        term_block_h += panel_inset + GAP_SECTION

    body_block_h = 0
    small = _load_font(
        scaled_size(int(fonts_cfg.get("body_start", 24)), scale, min_size=int(fonts_cfg.get("body_min", 20)))
    )
    if body:
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        blines = wrap_text(probe, body, small, cw - 56)[:2]
        body_block_h = measure_text_block(blines, small, line_gap=GAP_LINE_SM) + GAP_SECTION

    stack_bottom = content_limit
    if url:
        stack_bottom -= url_block_h

    box_y1 = stack_bottom
    box_y0 = box_y1 - box_h
    if box_y0 < cy0 + GAP_BLOCK:
        box_y0 = cy0 + GAP_BLOCK
        box_y1 = box_y0 + box_h
    if url and box_y1 + url_block_h > content_limit:
        box_y1 = max(box_y0 + box_h, content_limit - url_block_h)
        box_y0 = box_y1 - box_h

    upper_stack_bottom = box_y0 - GAP_SECTION
    if body:
        upper_stack_bottom -= body_block_h
    if term_guides:
        upper_stack_bottom -= term_block_h
    y_max_for_titles = max(cy0 + GAP_BLOCK, upper_stack_bottom - GAP_BLOCK)

    def _highlighter(draw_obj: ImageDraw.ImageDraw, **kwargs: Any) -> int:
        return _draw_header_highlighter(draw_obj, **kwargs)

    y = draw_template_header(
        draw,
        frame=frame,
        palette=palette,
        eyebrow=eyebrow,
        headline=headline,
        bottom_limit=y_max_for_titles,
        fit_font_lines_fn=lambda d, t, mw, **kw: fit_font_lines(d, t, mw, load_font_fn=_load_font, **kw),
        line_height_fn=line_height,
        draw_highlighter_title_fn=_highlighter,
        fill_scale_fn=fill_scale,
        scaled_size_fn=scaled_size,
        gap_block=GAP_BLOCK,
        gap_line_md=GAP_LINE_MD,
        gap_line_lg=GAP_LINE_LG,
        gap_section=GAP_SECTION,
    )

    if term_guides and y < y_max_for_titles:
        y = _draw_term_guide_panel(
            draw,
            cx0=cx0,
            cx1=cx1,
            y=y,
            guides=term_guides,
            bottom_limit=min(y_max_for_titles, box_y0 - GAP_BLOCK),
            panel_inset=panel_inset,
            title=str(term_cfg.get("title", "쉬운 말로")),
            title_size=int(fonts_cfg.get("term_title", 22)),
            body_size=int(fonts_cfg.get("term_body", 20)),
            panel_radius=int(term_cfg.get("panel_radius", 12)),
            max_guides=int(term_cfg.get("max_guides", 2)),
            max_body_lines=int(term_cfg.get("max_body_lines", 3)),
            load_font_fn=_load_font,
        )

    if body and y < box_y0 - GAP_BLOCK:
        blines = wrap_text(draw, body, small, panel_x1 - panel_x0 - panel_inset)[:2]
        for line in blines:
            if y + line_height(small, GAP_LINE_SM) > box_y0 - GAP_BLOCK:
                break
            draw.text((panel_x0, y), line, font=small, fill=INK_BODY)
            y += line_height(small, GAP_LINE_SM)

    if y < box_y0 - GAP_SECTION:
        sep_y = box_y0 - GAP_SECTION // 2
        draw.line(
            [(panel_x0, sep_y), (panel_x1, sep_y)],
            fill=DOT_GRAY,
            width=int(layout_cfg.get("separator_width", 2)),
        )

    cta_label = cta or str(defaults.get("cta", "원문 뉴스 보기"))
    draw_cta_action_panel(
        draw,
        x0=panel_x0,
        x1=panel_x1,
        y0=box_y0,
        y1=box_y1,
        label=cta_label,
        fill=tuple(palette.accent),
        text_fill=BRAND_ACCENT,
        radius=int(panel_cfg.get("radius", 14)),
        inset_panel=int(panel_cfg.get("inset_panel", panel_inset)),
        gap_line_sm=GAP_LINE_SM,
        fit_font_lines_fn=lambda d, t, mw, **kw: fit_font_lines(
            d,
            t,
            mw,
            start_size=int(panel_cfg.get("label_start", 40)),
            min_size=int(panel_cfg.get("label_min", 28)),
            load_font_fn=_load_font,
            **kw,
        ),
        measure_text_block_fn=lambda _d, ls, f: measure_text_block(ls, f, line_gap=GAP_LINE_SM),
        line_height_fn=line_height,
    )

    if url:
        display_max = int(url_cfg.get("display_max", 34))
        display = (url.replace("https://", "").replace("http://", ""))[:display_max]
        if len(ctx.source_url or "") > display_max:
            display = display[: display_max - 3] + "..."
        ut = f"{url_cfg.get('prefix', '앱에서 링크 · ')}{display}"
        url_y = max(box_y1 + GAP_LINE_LG, box_y0 + box_h + GAP_LINE_SM)
        url_y = min(url_y, content_limit - url_line_h - GAP_BLOCK)
        draw.text((panel_x0, url_y), ut, font=uf, fill=INK_BODY)

    if has_mascot and ctx.mascot is not None:
        return _paste_mascot_zone(
            canvas,
            ctx.mascot,
            speech,
            zone_top=mascot_top,
            zone_bottom=mascot_bottom,
            align="center",
        )
    return canvas.convert("RGB")


def render_template_numbered(ctx: Any) -> Image.Image:
    """`template_numbered.json` 기반 번호 목록 슬라이드."""
    from app.policy_cardnews.template.dispatch import (
        _content_and_mascot_bounds,
        _load_font,
        _paste_mascot_zone,
    )

    config, canvas, draw, frame, cx0, cy0, cx1, cy1, cw = _new_canvas(ctx, "template_numbered")
    slide = ctx.slide
    palette = ctx.palette
    defaults = config.get("defaults") or {}
    layout = config.get("layout") or {}
    fonts = config.get("fonts") or {}

    max_items = int(layout.get("max_items", 4))
    panel_inset = int(layout.get("panel_inset", INSET_PANEL))
    gap_row = int(layout.get("gap_row", GAP_ROW))
    items = _slide_items(slide)[:max_items]
    has_mascot = ctx.mascot is not None and len(items) <= int(layout.get("mascot_max_items", 3))
    _, body_bottom, mascot_top, mascot_bottom = _content_and_mascot_bounds(cy0, cy1, has_mascot)

    eyebrow = str(slide.get("eyebrow") or defaults.get("eyebrow", "한 장 요약")).strip()
    headline = str(slide.get("headline") or "").strip()
    y = _draw_slide_header(
        draw,
        frame=frame,
        palette=palette,
        eyebrow=eyebrow,
        headline=headline,
        bottom_limit=body_bottom,
        load_font_fn=_load_font,
    )

    n = max(len(items), 1)
    body_h = body_bottom - y
    row_h = max(int(layout.get("row_min_h", 48)), (body_h - gap_row * max(0, n - 1)) // n)
    scale = fill_scale(
        int(layout.get("scale_base_per_row", 64)) * n,
        body_h,
        max_scale=float(layout.get("scale_max", 1.65)),
    )
    title_f = _load_font(
        scaled_size(
            int(fonts.get("row_title_start", 36)),
            scale,
            min_size=int(fonts.get("row_title_min", 28)),
            max_size=int(fonts.get("row_title_max", 48)),
        ),
        bold=True,
    )
    max_wrap = int(layout.get("max_wrap_lines", 3))

    for index, item in enumerate(items):
        row_y0 = y + index * (row_h + gap_row)
        row_y1 = min(body_bottom, row_y0 + row_h)
        if row_y0 >= body_bottom - GAP_BLOCK:
            break
        inner_h = row_y1 - row_y0
        label = str(item.get("label") or "").strip()
        text = str(item.get("text") or "").strip()
        row_title = f"{label} · {text}".strip(" ·") if label else text

        num_size = scaled_size(
            int(fonts.get("num_start", 30)),
            scale,
            min_size=int(fonts.get("num_min", 24)),
            max_size=int(fonts.get("num_max", 38)),
        )
        num_r = max(26, int(inner_h * 0.26))
        num_x = cx0 + panel_inset // 2
        num_y = row_y0 + (inner_h - num_r * 2) // 2
        draw.ellipse((num_x, num_y, num_x + num_r * 2, num_y + num_r * 2), fill=tuple(palette.accent))
        nf = _load_font(num_size, bold=True)
        num_t = f"{index + 1}"
        nw = int(draw.textlength(num_t, font=nf))
        draw.text(
            (num_x + num_r - nw // 2, num_y + num_r - line_height(nf, 0) // 2),
            num_t,
            font=nf,
            fill=BRAND_ACCENT,
        )

        text_x0 = cx0 + num_r * 2 + GAP_SECTION
        text_x1 = cx1 - panel_inset
        text_w = text_x1 - text_x0
        wrapped = wrap_text(draw, row_title, title_f, text_w)[:max_wrap]
        block_h = measure_text_block(wrapped, title_f, line_gap=GAP_LINE_MD)
        ty = row_y0 + max(GAP_BLOCK, (inner_h - block_h) // 2)
        for line in wrapped:
            lw = int(draw.textlength(line, font=title_f))
            draw.text((text_x0 + (text_w - lw) // 2, ty), line, font=title_f, fill=INK)
            ty += line_height(title_f, GAP_LINE_MD)

        if index < len(items) - 1:
            sep_y = row_y1 + gap_row // 2
            draw.line(
                [
                    (cx0 + int(layout.get("separator_inset_left", 56)), sep_y),
                    (cx1 - panel_inset, sep_y),
                ],
                fill=DOT_GRAY,
                width=int(layout.get("separator_width", 2)),
            )

    if has_mascot:
        speech = str(slide.get("speech") or defaults.get("speech", "핵심만!"))[
            : int(defaults.get("speech_max_len", 18))
        ]
        return _paste_mascot_zone(
            canvas,
            ctx.mascot,
            speech,
            zone_top=mascot_top,
            zone_bottom=mascot_bottom,
            align="left",
        )
    return canvas.convert("RGB")


def render_template_three_col(ctx: Any) -> Image.Image:
    """`template_three_col.json` 기반 3열 슬라이드."""
    from app.policy_cardnews.template.dispatch import (
        _content_and_mascot_bounds,
        _load_font,
        _paste_mascot_zone,
    )

    config, canvas, draw, frame, cx0, cy0, cx1, cy1, cw = _new_canvas(ctx, "template_three_col")
    slide = ctx.slide
    palette = ctx.palette
    defaults = config.get("defaults") or {}
    layout = config.get("layout") or {}
    fonts = config.get("fonts") or {}

    max_items = int(layout.get("max_items", 3))
    panel_inset = int(layout.get("panel_inset", INSET_PANEL))
    col_gap = int(layout.get("col_gap", GAP_COL))
    items = _slide_items(slide)[:max_items]
    has_mascot = ctx.mascot is not None
    _, body_bottom, mascot_top, mascot_bottom = _content_and_mascot_bounds(cy0, cy1, has_mascot)

    eyebrow = str(slide.get("eyebrow") or "").strip()
    headline = str(slide.get("headline") or defaults.get("headline", "핵심만 정리")).strip()
    y = _draw_slide_header(
        draw,
        frame=frame,
        palette=palette,
        eyebrow=eyebrow,
        headline=headline,
        bottom_limit=body_bottom,
        load_font_fn=_load_font,
    )

    n_cols = max(len(items), 1)
    col_w = (cw - col_gap * (n_cols - 1)) // n_cols
    grid_w = n_cols * col_w + col_gap * (n_cols - 1)
    grid_x0 = _center_block_x(grid_w, cx0, cx1)
    col_top = y + GAP_BLOCK
    col_bottom = body_bottom
    col_h = col_bottom - col_top
    label_prefix = str(defaults.get("label_prefix", "항목"))

    for col_index, item in enumerate(items):
        col_x0 = grid_x0 + col_index * (col_w + col_gap)
        draw.rounded_rectangle(
            (col_x0, col_top, col_x0 + col_w, col_bottom),
            radius=int(layout.get("panel_radius", 14)),
            fill=GRAY_PANEL,
        )
        pad = panel_inset
        inner_w = col_w - pad * 2

        label = str(item.get("label") or f"{label_prefix}{col_index + 1}").strip()
        text = str(item.get("text") or "").strip()

        badge = max(
            int(layout.get("badge_min", 44)),
            min(int(layout.get("badge_max", 56)), int(col_h * float(layout.get("badge_ratio", 0.13)))),
        )
        badge_y = col_top + pad
        cx_center = col_x0 + col_w // 2
        draw.ellipse(
            (cx_center - badge // 2, badge_y, cx_center + badge // 2, badge_y + badge),
            fill=tuple(palette.accent),
        )
        nf = _load_font(int(fonts.get("badge_num_start", 22)), bold=True)
        num = f"{col_index + 1:02d}"
        nw = int(draw.textlength(num, font=nf))
        draw.text((cx_center - nw // 2, badge_y + badge // 4), num, font=nf, fill=BRAND_ACCENT)

        label_h = max(int(layout.get("label_h_min", 36)), int(col_h * float(layout.get("label_h_ratio", 0.18))))
        label_font, label_lines = _fit_text_in_rect(
            draw,
            label,
            inner_w,
            label_h,
            start_size=int(fonts.get("label_start", 32)),
            min_size=int(fonts.get("label_min", 24)),
            line_gap=GAP_LINE_SM,
            load_font_fn=_load_font,
            bold=True,
        )
        ly = badge_y + badge + GAP_LINE_MD
        _draw_centered_lines(
            draw,
            lines=label_lines,
            font=label_font,
            x0=col_x0 + pad,
            width=inner_w,
            y=ly,
            fill=INK,
            line_gap=GAP_LINE_SM,
        )

        content_top = ly + label_h + GAP_LINE_SM
        content_h = max(40, col_bottom - content_top - pad)
        body_font, body_lines = _fit_text_in_rect(
            draw,
            text,
            inner_w,
            content_h,
            start_size=int(fonts.get("body_start", 30)),
            min_size=int(fonts.get("body_min", 22)),
            line_gap=GAP_LINE_MD,
            load_font_fn=_load_font,
        )
        body_block_h = measure_text_block(body_lines, body_font, line_gap=GAP_LINE_MD)
        ty_text = content_top + max(0, (content_h - body_block_h) // 2)
        _draw_centered_lines(
            draw,
            lines=body_lines,
            font=body_font,
            x0=col_x0 + pad,
            width=inner_w,
            y=ty_text,
            fill=INK_BODY,
            line_gap=GAP_LINE_MD,
        )

    if has_mascot:
        speech = str(slide.get("speech") or defaults.get("speech", "핵심포인트!"))[
            : int(defaults.get("speech_max_len", 18))
        ]
        return _paste_mascot_zone(
            canvas,
            ctx.mascot,
            speech,
            zone_top=mascot_top,
            zone_bottom=mascot_bottom,
            align="left",
        )
    return canvas.convert("RGB")


def render_template_grid(ctx: Any) -> Image.Image:
    """`template_grid.json` 기반 2×2 그리드 슬라이드."""
    config, canvas, draw, frame, cx0, cy0, cx1, cy1, cw = _new_canvas(ctx, "template_grid")
    slide = ctx.slide
    palette = ctx.palette
    defaults = config.get("defaults") or {}
    layout = config.get("layout") or {}
    fonts = config.get("fonts") or {}

    frame_cfg = config.get("frame") or {}
    content_pad = int(frame_cfg.get("content_pad", CONTENT_PAD))
    max_items = int(layout.get("max_items", 4))
    gap = int(layout.get("gap_tile", GAP_TILE))
    tile_pad = int(layout.get("tile_pad", INSET_TILE))
    items = _slide_items(slide)[:max_items]
    body_bottom = cy1 - content_pad // 2

    eyebrow = str(slide.get("eyebrow") or "").strip()
    headline = str(slide.get("headline") or defaults.get("headline", "이렇게 확인하세요")).strip()
    from app.policy_cardnews.template.dispatch import _load_font

    y = _draw_slide_header(
        draw,
        frame=frame,
        palette=palette,
        eyebrow=eyebrow,
        headline=headline,
        bottom_limit=body_bottom,
        load_font_fn=_load_font,
    )

    tile_w = (cw - gap) // 2
    rows = 2
    grid_h = body_bottom - y
    tile_h = max(int(layout.get("tile_min_h", 120)), (grid_h - gap) // rows)
    grid_total_h = tile_h * rows + gap
    grid_y0 = y + max(0, (grid_h - grid_total_h) // 2)
    grid_w = tile_w * 2 + gap
    grid_x0 = _center_block_x(grid_w, cx0, cx1)
    label_prefix = str(defaults.get("label_prefix", "포인트"))

    for index, item in enumerate(items):
        col = index % 2
        row = index // 2
        tx0 = grid_x0 + col * (tile_w + gap)
        ty0 = grid_y0 + row * (tile_h + gap)
        tx1 = tx0 + tile_w
        ty1 = min(body_bottom, ty0 + tile_h)
        draw.rounded_rectangle(
            (tx0, ty0, tx1, ty1),
            radius=int(layout.get("panel_radius", 14)),
            fill=GRAY_PANEL,
        )

        label = str(item.get("label") or f"{label_prefix}{index + 1}").strip()
        text = str(item.get("text") or "").strip()
        inner_x0 = tx0 + tile_pad
        inner_x1 = tx1 - tile_pad
        inner_w = inner_x1 - inner_x0

        ribbon_h = max(int(layout.get("ribbon_min_h", 52)), int((ty1 - ty0) * float(layout.get("ribbon_ratio", 0.28))))
        draw.rectangle((tx0, ty0, tx1, ty0 + ribbon_h), fill=tuple(palette.accent))

        label_font, label_lines = _fit_text_in_rect(
            draw,
            label,
            inner_w,
            ribbon_h - tile_pad,
            start_size=int(fonts.get("label_start", 42)),
            min_size=int(fonts.get("label_min", 30)),
            line_gap=GAP_LINE_SM,
            load_font_fn=_load_font,
            bold=True,
        )
        label_block_h = measure_text_block(label_lines, label_font, line_gap=GAP_LINE_SM)
        ly = ty0 + max(tile_pad // 2, (ribbon_h - label_block_h) // 2)
        _draw_centered_lines(
            draw,
            lines=label_lines,
            font=label_font,
            x0=inner_x0,
            width=inner_w,
            y=ly,
            fill=BRAND_ACCENT,
            line_gap=GAP_LINE_SM,
        )

        content_top = ty0 + ribbon_h + tile_pad
        content_bottom = ty1 - tile_pad
        content_h = max(40, content_bottom - content_top)
        body_font, body_lines = _fit_text_in_rect(
            draw,
            text,
            inner_w,
            content_h,
            start_size=int(fonts.get("body_start", 44)),
            min_size=int(fonts.get("body_min", 30)),
            line_gap=GAP_LINE_MD,
            load_font_fn=_load_font,
        )
        body_block_h = measure_text_block(body_lines, body_font, line_gap=GAP_LINE_MD)
        ty_text = content_top + max(0, (content_h - body_block_h) // 2)
        _draw_centered_lines(
            draw,
            lines=body_lines,
            font=body_font,
            x0=inner_x0,
            width=inner_w,
            y=ty_text,
            fill=INK,
            line_gap=GAP_LINE_MD,
        )

    return canvas.convert("RGB")
