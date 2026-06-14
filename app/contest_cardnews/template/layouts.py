from __future__ import annotations

from typing import Any

from PIL import ImageDraw

from app.contest_cardnews.constants import (
    CARD_INNER_PAD,
    ELEMENT_GAP,
    GAP_MD,
    GAP_SM,
    INK,
    INK_SOFT,
    LABEL_STRIP_H,
    ROW_GAP,
    STAR_PEACH,
    TITLE_TOP_PAD,
)
from app.contest_cardnews.template.base import (
    ContestRenderContext,
    centered_column,
    content_bottom_y,
    draw_accent_pill,
    draw_centered_in_band,
    draw_centered_lines,
    draw_centered_title,
    draw_four_point_star,
    draw_point_footer,
    draw_source_url_footer,
    draw_wrapped_block,
    fit_font_single_line,
    inner_content_rect,
    load_font,
    mascot_zone,
    new_canvas,
    paste_mascot_in_zone,
    slide_items,
    vertical_center_y,
)
from app.policy_cardnews.template.draw import line_height, measure_text_block


def _has_mascot(ctx: ContestRenderContext) -> bool:
    return ctx.mascot is not None


def _finish(
    canvas,
    ctx: ContestRenderContext,
    content_rect: tuple[int, int, int, int],
    *,
    corner: str = "right",
):
    if _has_mascot(ctx):
        cx0, cy0, cx1, cy1 = content_rect
        zone = mascot_zone(cx0, cy0, cx1, cy1)
        canvas = paste_mascot_in_zone(
            canvas,
            ctx.mascot,
            str(ctx.slide.get("speech") or ""),
            zone,
            palette=ctx.palette,
            corner=corner,
        )
    return canvas


def _estimate_centered_stack_height(
    draw: ImageDraw.ImageDraw,
    parts: list[tuple[str, int, int, bool, tuple[int, int, int]]],
    width: int,
) -> int:
    """parts: (text, start_size, min_size, bold, fill_ignored)."""
    total = 0
    for text, start, min_sz, bold, _ in parts:
        if not text:
            continue
        _, lines = fit_font_single_line(
            draw, text, width, start_size=start, min_size=min_sz, bold=bold, max_lines=3,
        )
        font = load_font(min_sz, bold=bold, extra_bold=bold)
        total += measure_text_block(lines, font, line_gap=GAP_SM) + ELEMENT_GAP
    return max(0, total - ELEMENT_GAP)


def render_contest_cover(ctx: ContestRenderContext):
    slide = ctx.slide
    palette = ctx.palette
    canvas, draw, rect = new_canvas(palette)
    col = centered_column(inner_content_rect(rect))
    ix0, iy0, ix1, iy1 = col
    cw = ix1 - ix0
    has_mascot = _has_mascot(ctx)
    bottom = content_bottom_y(iy1, has_mascot=has_mascot, has_point=False)

    eyebrow = str(slide.get("eyebrow") or slide.get("subtext") or "").strip()
    headline = str(slide.get("headline") or "").strip()
    highlight = str(slide.get("highlight") or "").strip()
    pill = str(slide.get("body") or slide.get("cta") or "").strip()

    pill_h = 0
    if pill:
        _, plines = fit_font_single_line(
            draw, pill, cw - 100, start_size=34, min_size=26, bold=True, max_lines=2,
        )
        pf = load_font(26, bold=True)
        pill_h = measure_text_block(plines, pf, line_gap=8) + 36

    text_bottom = bottom - pill_h - ELEMENT_GAP
    parts: list[tuple[str, int, int, bool, tuple[int, int, int]]] = []
    if eyebrow:
        parts.append((eyebrow, 38, 28, False, INK))
    if headline:
        parts.append((headline, 72, 40, True, palette.accent))
    if highlight and highlight != headline:
        parts.append((highlight, 72, 40, True, INK))

    stack_h = _estimate_centered_stack_height(draw, parts, cw)
    y = vertical_center_y(iy0, text_bottom, stack_h)

    draw_four_point_star(draw, ix0 + 4, iy0 + 2, 12, STAR_PEACH)
    draw_four_point_star(draw, ix1 - 28, iy0 + 6, 10, STAR_PEACH)

    if eyebrow:
        font, lines = fit_font_single_line(draw, eyebrow, cw, start_size=38, min_size=28, max_lines=2)
        y = draw_centered_lines(draw, cx0=ix0, cx1=ix1, y=y, lines=lines, font=font, fill=INK, max_y=text_bottom) + ELEMENT_GAP

    if headline:
        font, lines = fit_font_single_line(
            draw, headline, cw - 8, start_size=72, min_size=40, bold=True, max_lines=2,
        )
        y = draw_centered_lines(
            draw, cx0=ix0, cx1=ix1, y=y, lines=lines, font=font, fill=palette.accent, max_y=text_bottom,
        ) + ELEMENT_GAP

    if highlight and highlight != headline:
        font, lines = fit_font_single_line(
            draw, highlight, cw - 8, start_size=72, min_size=40, bold=True, max_lines=2,
        )
        y = draw_centered_lines(
            draw, cx0=ix0, cx1=ix1, y=y, lines=lines, font=font, fill=INK, max_y=text_bottom,
        ) + ELEMENT_GAP

    if pill:
        draw_accent_pill(
            draw, cx0=ix0 + 36, cx1=ix1 - 36, y0=iy0, y1=bottom - ELEMENT_GAP,
            text=pill, palette=palette, start_size=34, min_size=26,
        )

    return _finish(canvas, ctx, rect, corner="right")


def render_contest_headline(ctx: ContestRenderContext):
    slide = ctx.slide
    palette = ctx.palette
    canvas, draw, rect = new_canvas(palette)
    col = centered_column(inner_content_rect(rect))
    ix0, iy0, ix1, iy1 = col
    bottom = content_bottom_y(iy1, has_point=True)

    main = str(slide.get("headline") or "").strip()
    highlight = str(slide.get("highlight") or "").strip()
    if highlight and highlight not in main:
        main = f"{main} {highlight}".strip()
    if not main:
        return canvas

    title_h = 52
    _, main_lines = fit_font_single_line(
        draw, main, ix1 - ix0, start_size=54, min_size=36, bold=True, max_lines=5,
    )
    mf = load_font(36, bold=True)
    main_h = measure_text_block(main_lines, mf, line_gap=GAP_SM)
    y = vertical_center_y(iy0 + title_h, bottom - 60, main_h)

    draw_centered_title(draw, cx0=ix0, cx1=ix1, y=iy0 + 8, text="핵심 내용", palette=palette, size=42)
    draw_wrapped_block(
        draw, main, x0=ix0, x1=ix1, y=y, max_y=bottom - 50,
        start_size=54, min_size=36, bold=True, center=True, max_lines=6,
    )

    body = str(slide.get("body") or "").strip()
    if body:
        draw_wrapped_block(
            draw, body, x0=ix0, x1=ix1, y=bottom - 90, max_y=bottom - 12,
            start_size=34, min_size=28, fill=INK_SOFT, center=True, max_lines=2,
        )

    point = str(slide.get("point") or "").strip()
    if point:
        draw_point_footer(draw, cx0=ix0, cx1=ix1, cy1=iy1, text=point, palette=palette)
    return canvas


def render_contest_body(ctx: ContestRenderContext):
    slide = ctx.slide
    palette = ctx.palette
    canvas, draw, rect = new_canvas(palette)
    col = centered_column(inner_content_rect(rect))
    ix0, iy0, ix1, iy1 = col
    bottom = content_bottom_y(iy1, has_point=True)

    body = str(slide.get("body") or slide.get("headline") or "").strip()
    if not body:
        return canvas

    title_h = 56
    body_font, body_lines = fit_font_single_line(
        draw, body, ix1 - ix0 - 48, start_size=38, min_size=30, max_lines=12,
    )
    body_h = measure_text_block(body_lines, body_font, line_gap=GAP_SM) + 48
    box_y0 = vertical_center_y(iy0 + title_h, bottom, body_h)

    draw_centered_title(draw, cx0=ix0, cx1=ix1, y=iy0 + 6, text="공고 요약", palette=palette, size=42)
    draw.rounded_rectangle(
        (ix0, box_y0, ix1, box_y0 + body_h),
        radius=20,
        outline=palette.panel_border,
        width=2,
        fill=(255, 255, 255),
    )
    draw_wrapped_block(
        draw, body, x0=ix0 + 28, x1=ix1 - 28, y=box_y0 + 24, max_y=box_y0 + body_h - 20,
        start_size=38, min_size=30, center=True, max_lines=12,
    )

    point = str(slide.get("point") or "").strip()
    if point:
        draw_point_footer(draw, cx0=ix0, cx1=ix1, cy1=iy1, text=point, palette=palette)
    return canvas


def _draw_summary_cards(
    draw: ImageDraw.ImageDraw,
    *,
    items: list[dict[str, str]],
    ix0: int,
    ix1: int,
    y0: int,
    y1: int,
    palette: Any,
) -> None:
    """라벨+내용이 한 카드(네모) 안에 들어가는 요약 행."""
    rows: list[tuple[str, str]] = []
    for item in items:
        label = str(item.get("label") or "").strip()
        text = str(item.get("text") or "").strip()
        if text:
            rows.append((label or "안내", text))

    if not rows:
        return

    cw = ix1 - ix0
    strip_h = LABEL_STRIP_H
    pad = CARD_INNER_PAD
    row_heights: list[int] = []
    label_fonts: list = []
    label_lines_list: list[list[str]] = []
    value_fonts: list = []
    value_lines_list: list[list[str]] = []
    for label, text in rows:
        label_font, label_lines = fit_font_single_line(
            draw, label, cw - pad * 2, start_size=28, min_size=22, bold=True, max_lines=1,
        )
        value_font, tlines = fit_font_single_line(
            draw, text, cw - pad * 2, start_size=34, min_size=28, max_lines=3,
        )
        vlh = line_height(value_font, GAP_SM)
        vth = max(measure_text_block(tlines, value_font, line_gap=GAP_SM), vlh * max(1, len(tlines)))
        label_fonts.append(label_font)
        label_lines_list.append(label_lines)
        value_fonts.append(value_font)
        value_lines_list.append(tlines)
        row_heights.append(strip_h + pad + vth + pad)

    total_h = sum(row_heights) + ROW_GAP * (len(rows) - 1)
    y = vertical_center_y(y0, y1, total_h)

    for (label, _text), rh, label_font, label_lines, value_font, tlines in zip(
        rows, row_heights, label_fonts, label_lines_list, value_fonts, value_lines_list,
    ):
        card_y1 = y + rh
        draw.rounded_rectangle(
            (ix0, y, ix1, card_y1),
            radius=16,
            fill=(255, 255, 255),
            outline=palette.panel_border,
            width=2,
        )
        draw.rounded_rectangle(
            (ix0, y, ix1, y + strip_h),
            radius=16,
            fill=palette.accent,
        )
        if strip_h < rh:
            draw.rectangle((ix0, y + strip_h - 14, ix1, y + strip_h), fill=palette.accent)

        draw_centered_in_band(
            draw, cx0=ix0 + pad, cx1=ix1 - pad, y0=y, y1=y + strip_h,
            lines=label_lines, font=label_font, fill=(255, 255, 255),
        )
        draw_centered_in_band(
            draw, cx0=ix0 + pad, cx1=ix1 - pad, y0=y + strip_h + pad // 2, y1=card_y1 - pad // 2,
            lines=tlines, font=value_font, fill=INK,
        )
        y = card_y1 + ROW_GAP


def render_contest_table(ctx: ContestRenderContext):
    slide = ctx.slide
    palette = ctx.palette
    canvas, draw, rect = new_canvas(palette)
    col = centered_column(inner_content_rect(rect))
    ix0, iy0, ix1, iy1 = col
    items = slide_items(slide, max_items=4)
    bottom = content_bottom_y(iy1, has_point=True)

    title = str(slide.get("headline") or "").strip() or "한눈에 보기"
    title_bottom = draw_centered_title(
        draw, cx0=ix0, cx1=ix1, y=iy0 + TITLE_TOP_PAD, text=title, palette=palette, size=44, max_y=bottom,
    )
    cards_y0 = title_bottom + ELEMENT_GAP

    _draw_summary_cards(
        draw, items=items, ix0=ix0, ix1=ix1, y0=cards_y0, y1=bottom - ELEMENT_GAP, palette=palette,
    )

    point = str(slide.get("point") or "").strip()
    if point:
        draw_point_footer(draw, cx0=ix0, cx1=ix1, cy1=iy1, text=point, palette=palette)
    return canvas


def _draw_check_icon(draw: ImageDraw.ImageDraw, x: int, y: int, palette: Any) -> None:
    draw.rounded_rectangle((x, y, x + 34, y + 34), radius=6, outline=palette.accent, width=2)
    draw.line((x + 8, y + 18, x + 15, y + 25), fill=palette.accent, width=3)
    draw.line((x + 15, y + 25, x + 26, y + 11), fill=palette.accent, width=3)


def render_contest_checklist(ctx: ContestRenderContext):
    slide = ctx.slide
    palette = ctx.palette
    canvas, draw, rect = new_canvas(palette)
    col = centered_column(inner_content_rect(rect))
    ix0, iy0, ix1, iy1 = col
    items = slide_items(slide, max_items=4)
    bottom = content_bottom_y(iy1, has_point=True)

    if not items:
        return canvas

    title = str(slide.get("headline") or "").strip() or "지원 전 확인"
    title_bottom = draw_centered_title(
        draw, cx0=ix0, cx1=ix1, y=iy0 + TITLE_TOP_PAD, text=title, palette=palette, size=44,
    )
    y0 = title_bottom + ELEMENT_GAP

    row_heights: list[int] = []
    row_fonts: list = []
    row_lines: list[list[str]] = []
    text_x0 = ix0 + 62
    text_x1 = ix1 - CARD_INNER_PAD
    for item in items:
        text = str(item.get("text") or "").strip()
        font, lines = fit_font_single_line(
            draw, text, text_x1 - text_x0, start_size=32, min_size=26, max_lines=2,
        )
        lh = line_height(font, GAP_SM)
        th = max(measure_text_block(lines, font, line_gap=GAP_SM), lh * max(1, len(lines)))
        row_heights.append(max(64, th + CARD_INNER_PAD * 2))
        row_fonts.append(font)
        row_lines.append(lines)

    total_h = sum(row_heights) + ROW_GAP * (len(items) - 1)
    y = vertical_center_y(y0, bottom - ELEMENT_GAP, total_h)

    for item, rh, font, lines in zip(items, row_heights, row_fonts, row_lines):
        text = str(item.get("text") or "").strip()
        if not text or not lines:
            continue
        row_y1 = y + rh
        draw.rounded_rectangle(
            (ix0, y, ix1, row_y1),
            radius=14,
            fill=palette.panel,
            outline=palette.panel_border,
            width=2,
        )
        _draw_check_icon(draw, ix0 + 18, y + (rh - 34) // 2, palette)
        draw_centered_in_band(
            draw, cx0=text_x0, cx1=text_x1, y0=y + CARD_INNER_PAD // 2, y1=row_y1 - CARD_INNER_PAD // 2,
            lines=lines, font=font, fill=INK,
        )
        y = row_y1 + ROW_GAP

    point = str(slide.get("point") or "").strip()
    if point:
        draw_point_footer(draw, cx0=ix0, cx1=ix1, cy1=iy1, text=point, palette=palette)
    return canvas


def render_contest_three_col(ctx: ContestRenderContext):
    return render_contest_table(ctx)


def render_contest_cta(ctx: ContestRenderContext):
    slide = ctx.slide
    palette = ctx.palette
    canvas, draw, rect = new_canvas(palette)
    col = centered_column(inner_content_rect(rect))
    ix0, iy0, ix1, iy1 = col
    cw = ix1 - ix0
    has_mascot = _has_mascot(ctx)
    bottom = content_bottom_y(iy1, has_mascot=has_mascot, has_point=False)

    headline = str(slide.get("headline") or "").strip()
    highlight = str(slide.get("highlight") or "").strip()
    body = str(slide.get("body") or "").strip()
    cta = str(slide.get("cta") or "").strip()
    if not cta:
        cta = "공고 보러가기"
    source_url = (ctx.source_url or str(slide.get("source_url") or "")).strip()

    url_h = 54 if source_url else 0
    cta_probe_font, cta_lines = fit_font_single_line(
        draw, cta, cw - 120, start_size=36, min_size=28, bold=True, max_lines=2,
    )
    cta_h = 0
    if cta_lines:
        cta_h = measure_text_block(cta_lines, cta_probe_font, line_gap=GAP_SM) + 52

    content_bottom = bottom - url_h - cta_h - ELEMENT_GAP

    parts: list[tuple[str, int, int, bool, tuple[int, int, int]]] = []
    if headline:
        parts.append((headline, 50, 34, True, INK))
    if highlight:
        parts.append((highlight, 50, 34, True, palette.accent))
    if body:
        parts.append((body, 34, 28, False, INK_SOFT))

    stack_h = _estimate_centered_stack_height(draw, parts, cw)
    y = vertical_center_y(iy0, content_bottom, stack_h)

    if headline:
        y = draw_wrapped_block(
            draw, headline, x0=ix0, x1=ix1, y=y, max_y=content_bottom,
            start_size=50, min_size=34, bold=True, center=True, max_lines=2,
        ) + GAP_MD
    if highlight:
        y = draw_wrapped_block(
            draw, highlight, x0=ix0, x1=ix1, y=y, max_y=content_bottom,
            start_size=50, min_size=34, bold=True, fill=palette.accent, center=True, max_lines=2,
        ) + GAP_MD
    if body:
        y = draw_wrapped_block(
            draw, body, x0=ix0, x1=ix1, y=y, max_y=content_bottom,
            start_size=34, min_size=28, fill=INK_SOFT, center=True, max_lines=3,
        )

    if cta_lines and cta_h > 0:
        by1 = bottom - url_h - ELEMENT_GAP
        by0 = by1 - (cta_h - 12)
        draw_accent_pill(
            draw, cx0=ix0 + 40, cx1=ix1 - 40, y0=by0, y1=by1,
            text=cta, palette=palette, start_size=36, min_size=28,
        )

    if source_url:
        draw_source_url_footer(
            draw, cx0=ix0, cx1=ix1, y=bottom - url_h - 4, url=source_url,
            palette=palette, max_y=bottom - 6,
        )

    return _finish(canvas, ctx, rect, corner="right")
