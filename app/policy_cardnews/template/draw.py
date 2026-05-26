# 정책 카드뉴스 템플릿의 반복 그리기 로직

from __future__ import annotations

from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont


def draw_frame_base(
    *,
    canvas_width: int,
    canvas_height: int,
    outer_fill: tuple[int, int, int],
    offset_fill: tuple[int, int, int],
    white_rect: tuple[int, int, int, int],
    offset_px: int,
) -> Image.Image:
    canvas = Image.new("RGB", (canvas_width, canvas_height), outer_fill)
    draw = ImageDraw.Draw(canvas)
    gx0, gy0, gx1, gy1 = white_rect
    draw.rectangle((gx0 + offset_px, gy0 + offset_px, gx1 + offset_px, gy1 + offset_px), fill=offset_fill)
    draw.rectangle(white_rect, fill=(255, 255, 255))
    return canvas


def draw_highlighter_title(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    text: str,
    max_w: int,
    font: ImageFont.FreeTypeFont,
    highlight_fill: tuple[int, int, int],
    text_fill: tuple[int, int, int],
    wrap_fn: Callable[[ImageDraw.ImageDraw, str, ImageFont.FreeTypeFont, int], list[str]],
    line_height_fn: Callable[[ImageFont.FreeTypeFont, int], int],
    line_gap: int,
) -> int:
    lines = wrap_fn(draw, text, font, max_w)
    cy = y
    for line in lines[:3]:
        lw = int(draw.textlength(line, font=font))
        lx = x + (max_w - lw) // 2
        draw.rectangle(
            (lx - 8, cy + 6, lx + lw + 8, cy + line_height_fn(font, 4)),
            fill=highlight_fill,
        )
        draw.text((lx, cy), line, font=font, fill=text_fill)
        cy += line_height_fn(font, line_gap)
    return cy


def draw_cta_action_panel(
    draw: ImageDraw.ImageDraw,
    *,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
    label: str,
    fill: tuple[int, int, int],
    text_fill: tuple[int, int, int],
    radius: int,
    inset_panel: int,
    gap_line_sm: int,
    fit_font_lines_fn: Callable[..., tuple[ImageFont.FreeTypeFont, list[str]]],
    measure_text_block_fn: Callable[[ImageDraw.ImageDraw, list[str], ImageFont.FreeTypeFont], int],
    line_height_fn: Callable[[ImageFont.FreeTypeFont, int], int],
) -> None:
    # 그리드 타일 리본과 동일한 톤의 CTA 버튼(텍스트 자동 줄바꿈/중앙 정렬)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill)
    inner_h = y1 - y0
    font, lines = fit_font_lines_fn(
        draw,
        label,
        x1 - x0 - inset_panel * 2,
        max_lines=2,
        bold=True,
    )
    block_h = measure_text_block_fn(draw, lines, font)
    ty = y0 + max(inset_panel // 2, (inner_h - block_h) // 2)
    for line in lines:
        lw = int(draw.textlength(line, font=font))
        draw.text((x0 + (x1 - x0 - lw) // 2, ty), line, font=font, fill=text_fill)
        ty += line_height_fn(font, gap_line_sm)


def line_height(font: ImageFont.FreeTypeFont, gap: int = 0) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent + gap


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    value = (text or "").replace("\n", " ").strip()
    if not value:
        return []

    if " " in value:
        words = value.split()
        lines: list[str] = []
        cur = words[0]
        for word in words[1:]:
            trial = f"{cur} {word}"
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
        return lines

    lines: list[str] = []
    cur = ""
    for char in value:
        trial = cur + char
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = char
    if cur:
        lines.append(cur)
    return lines


def fit_font_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_w: int,
    *,
    start_size: int,
    min_size: int,
    max_lines: int,
    load_font_fn: Callable[..., ImageFont.FreeTypeFont],
    bold: bool = False,
    extra_bold: bool = False,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    value = (text or "").strip()
    if not value:
        font = load_font_fn(min_size, bold=bold, extra_bold=extra_bold)
        return font, []
    for size in range(start_size, min_size - 1, -2):
        font = load_font_fn(size, bold=bold, extra_bold=extra_bold)
        lines = wrap_text(draw, value, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
    font = load_font_fn(min_size, bold=bold, extra_bold=extra_bold)
    return font, wrap_text(draw, value, font, max_w)[:max_lines]


def measure_text_block(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    *,
    line_gap: int,
) -> int:
    if not lines:
        return 0
    return len(lines) * line_height(font, line_gap) - line_gap


def fill_scale(used_h: int, available_h: int, *, min_scale: float = 1.08, max_scale: float = 1.78) -> float:
    if available_h <= 0:
        return min_scale
    if used_h <= 0:
        return max_scale
    fill_ratio = used_h / available_h
    if fill_ratio < 0.78:
        return max_scale
    if fill_ratio >= 0.96:
        return min_scale
    ratio = available_h / used_h
    return max(min_scale, min(max_scale, ratio * 0.98))


def scaled_size(base: int, scale: float, *, density: float = 1.08, min_size: int = 18, max_size: int = 112) -> int:
    return max(min_size, min(max_size, int(base * density * scale)))


def draw_template_header(
    draw: ImageDraw.ImageDraw,
    *,
    frame: Any,
    palette: Any,
    eyebrow: str,
    headline: str,
    bottom_limit: int,
    fit_font_lines_fn: Callable[..., tuple[ImageFont.FreeTypeFont, list[str]]],
    line_height_fn: Callable[[ImageFont.FreeTypeFont, int], int],
    draw_highlighter_title_fn: Callable[..., int],
    fill_scale_fn: Callable[..., float],
    scaled_size_fn: Callable[..., int],
    gap_block: int,
    gap_line_md: int,
    gap_line_lg: int,
    gap_section: int,
) -> int:
    cx0, cy0, cx1, _ = frame.content
    cw = cx1 - cx0
    available = bottom_limit - cy0
    y = cy0 + gap_block

    if eyebrow:
        font, lines = fit_font_lines_fn(
            draw,
            eyebrow,
            cw - 24,
            start_size=scaled_size_fn(32, fill_scale_fn(36, available)),
            min_size=24,
            max_lines=2,
            bold=True,
        )
        for line in lines:
            lh = line_height_fn(font, gap_line_md) + 8
            if y + lh > bottom_limit - gap_block:
                break
            y = draw_highlighter_title_fn(
                draw,
                x=cx0,
                y=y,
                text=line,
                max_w=cw,
                font=font,
                highlight_fill=palette.offset,
                line_gap=gap_line_md,
            )
        y += gap_line_md

    if headline:
        font, lines = fit_font_lines_fn(
            draw,
            headline,
            cw - 16,
            start_size=scaled_size_fn(52, fill_scale_fn(72, available)),
            min_size=36,
            max_lines=2,
            extra_bold=True,
        )
        for line in lines:
            lh = line_height_fn(font, gap_line_lg) + 8
            if y + lh > bottom_limit - gap_block:
                break
            y = draw_highlighter_title_fn(
                draw,
                x=cx0,
                y=y,
                text=line,
                max_w=cw,
                font=font,
                highlight_fill=palette.offset,
                line_gap=gap_line_lg,
            )
    return min(y + gap_section, bottom_limit)

