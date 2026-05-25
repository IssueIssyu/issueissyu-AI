from __future__ import annotations

from PIL import ImageDraw, ImageFont


def draw_text_stroked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int],
    stroke_fill: tuple[int, int, int],
    stroke_width: int = 4,
) -> None:
    x, y = xy
    if stroke_width > 0:
        for ox in range(-stroke_width, stroke_width + 1):
            for oy in range(-stroke_width, stroke_width + 1):
                if ox * ox + oy * oy > stroke_width * stroke_width:
                    continue
                draw.text((x + ox, y + oy), text, font=font, fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)


def draw_sticker_lines(
    draw: ImageDraw.ImageDraw,
    *,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    fill: tuple[int, int, int],
    stroke_fill: tuple[int, int, int],
    stroke_width: int = 5,
    gap: int = 8,
    center_width: int | None = None,
    line_height_fn,
) -> int:
    cursor = y
    for line in lines:
        line_w = int(draw.textlength(line, font=font))
        lx = x + (center_width - line_w) // 2 if center_width is not None else x
        draw_text_stroked(
            draw,
            (lx, cursor),
            line,
            font,
            fill=fill,
            stroke_fill=stroke_fill,
            stroke_width=stroke_width,
        )
        cursor += line_height_fn(font, gap)
    return cursor


def draw_highlight_bar(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    fill: tuple[int, int, int] = (214, 233, 255),
) -> None:
    draw.rounded_rectangle((x, y, x + width, y + height), radius=10, fill=fill)


def draw_label_pill(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = (29, 135, 255),
    text_fill: tuple[int, int, int] = (255, 255, 255),
) -> tuple[int, int]:
    pill_w = int(draw.textlength(text, font=font)) + 28
    pill_h = 36
    draw.rounded_rectangle((x, y, x + pill_w, y + pill_h), radius=12, fill=fill)
    draw.text((x + 14, y + 7), text, font=font, fill=text_fill)
    return pill_w, pill_h
