from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.contest_cardnews.constants import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CARD_INSET,
    CONTENT_PAD,
    ELEMENT_GAP,
    FONT_SCALE,
    GAP_LG,
    GAP_MD,
    GAP_SM,
    INK,
    INK_SOFT,
    INNER_PAD_X,
    INNER_PAD_Y,
    MASCOT_GAP,
    MASCOT_ZONE_H,
    SPEECH_ICON_GAP,
    NOTE_PINK,
    POINT_FOOTER_H,
    STAR_PEACH,
)
from app.policy_cardnews.mascot import BUBBLE_FILL, BUBBLE_OUTLINE, draw_classic_speech_bubble
from app.contest_cardnews.template.chrome import draw_browser_chrome
from app.contest_cardnews.template.palette import ContestPalette
from app.policy_cardnews.template.draw import (
    fit_font_lines,
    line_height,
    measure_text_block,
    wrap_text,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FONT_DIR = _REPO_ROOT / "app" / "assets" / "fonts"
_CONTEST_FONT_REGULAR = "Hakgyoansim Dunggeunmiso TTF R.ttf"
_CONTEST_FONT_BOLD = "Hakgyoansim Dunggeunmiso TTF B.ttf"


@dataclass
class ContestRenderContext:
    slide: dict[str, Any]
    palette: ContestPalette
    mascot: Image.Image | None = None
    source_url: str = ""


def content_bottom_y(
    cy1: int,
    *,
    has_mascot: bool = False,
    has_point: bool = False,
) -> int:
    """본문·도형이 들어갈 하한 (캐릭터·POINT 영역 제외)."""
    y = cy1
    if has_point:
        y -= POINT_FOOTER_H
    if has_mascot:
        y -= MASCOT_ZONE_H + MASCOT_GAP
    return y


def mascot_zone(cx0: int, cy0: int, cx1: int, cy1: int) -> tuple[int, int, int, int]:
    """하단 캐릭터 전용 슬롯 (본문과 겹치지 않음)."""
    zone_y1 = cy1 - POINT_FOOTER_H if cy1 > POINT_FOOTER_H + MASCOT_ZONE_H else cy1
    zone_y0 = zone_y1 - MASCOT_ZONE_H
    return (cx0, max(cy0, zone_y0), cx1, zone_y1)


@lru_cache(maxsize=64)
def load_font(size: int, *, bold: bool = False, extra_bold: bool = False) -> ImageFont.FreeTypeFont:
    """공모전 카드뉴스 전용: 학교안심 둥근미소 R/B만 사용."""
    size = max(18, int(size * FONT_SCALE))
    name = _CONTEST_FONT_BOLD if (bold or extra_bold) else _CONTEST_FONT_REGULAR
    path = _FONT_DIR / name
    if path.is_file():
        return ImageFont.truetype(str(path), size=size)
    # 전용 폰트가 없을 때 한글 지원 가능한 Pretendard를 우선 폴백으로 사용한다.
    for fallback_name in (
        "Pretendard-Bold.otf",
        "Pretendard-Bold.ttf",
        "Pretendard-Medium.otf",
        "Pretendard-Regular.otf",
    ):
        fallback_path = _FONT_DIR / fallback_name
        if fallback_path.is_file():
            return ImageFont.truetype(str(fallback_path), size=size)
    return ImageFont.load_default()


def new_canvas(palette: ContestPalette) -> tuple[Image.Image, ImageDraw.ImageDraw, tuple[int, int, int, int]]:
    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), palette.outer)
    draw = ImageDraw.Draw(canvas)
    wx0 = CARD_INSET
    wy0 = CARD_INSET
    wx1 = CANVAS_WIDTH - CARD_INSET
    wy1 = CANVAS_HEIGHT - CARD_INSET
    draw.rectangle((wx0, wy0, wx1, wy1), fill=(255, 255, 255))
    content_top = draw_browser_chrome(draw, (wx0, wy0, wx1, wy1), palette)
    cx0 = wx0 + CONTENT_PAD
    cy0 = content_top + GAP_SM
    cx1 = wx1 - CONTENT_PAD
    cy1 = wy1 - CONTENT_PAD
    return canvas, draw, (cx0, cy0, cx1, cy1)


def inner_content_rect(
    rect: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """본문을 화면 중앙으로 모으기 위한 추가 인셋."""
    x0, y0, x1, y1 = rect
    return (
        x0 + INNER_PAD_X,
        y0 + INNER_PAD_Y,
        x1 - INNER_PAD_X,
        y1 - INNER_PAD_Y,
    )


def centered_column(
    rect: tuple[int, int, int, int],
    *,
    width_ratio: float = 0.9,
) -> tuple[int, int, int, int]:
    """가로 중앙 정렬된 본문 컬럼."""
    x0, y0, x1, y1 = rect
    w = max(200, int((x1 - x0) * width_ratio))
    cx = (x0 + x1) // 2
    return (cx - w // 2, y0, cx + w // 2, y1)


def vertical_center_y(y0: int, y1: int, block_h: int) -> int:
    return y0 + max(0, (y1 - y0 - block_h) // 2)


def fit_font_single_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_w: int,
    *,
    start_size: int,
    min_size: int,
    bold: bool = False,
    max_lines: int = 2,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    value = (text or "").strip()
    if not value:
        return load_font(min_size, bold=bold), []
    for size in range(start_size, min_size - 1, -2):
        font, lines = fit_font_lines(
            draw,
            value,
            max_w,
            start_size=size,
            min_size=size,
            max_lines=max_lines,
            load_font_fn=load_font,
            bold=bold,
            extra_bold=bold,
        )
        if lines:
            return font, lines
    font = load_font(min_size, bold=bold)
    return font, fit_font_lines(
        draw, value, max_w, start_size=min_size, min_size=min_size,
        max_lines=max_lines, load_font_fn=load_font, bold=bold, extra_bold=bold,
    )[1]


def draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    *,
    cx0: int,
    cx1: int,
    y: int,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    max_y: int,
) -> int:
    cy = y
    for line in lines:
        lh = line_height(font, GAP_SM)
        if cy + lh > max_y:
            break
        lw = int(draw.textlength(line, font=font))
        tx = cx0 + (cx1 - cx0 - lw) // 2
        draw.text((tx, cy), line, font=font, fill=fill)
        cy += lh
    return cy


def draw_centered_in_band(
    draw: ImageDraw.ImageDraw,
    *,
    cx0: int,
    cx1: int,
    y0: int,
    y1: int,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> int:
    """밴드(y0~y1) 안에 텍스트 블록을 세로·가로 중앙 정렬."""
    if not lines or y1 <= y0:
        return y0
    block_h = measure_text_block(lines, font, line_gap=GAP_SM)
    cy = y0 + max(0, (y1 - y0 - block_h) // 2)
    for line in lines:
        lh = line_height(font, GAP_SM)
        if cy + lh > y1:
            break
        lw = int(draw.textlength(line, font=font))
        tx = cx0 + (cx1 - cx0 - lw) // 2
        draw.text((tx, cy), line, font=font, fill=fill)
        cy += lh
    return cy


def draw_centered_title(
    draw: ImageDraw.ImageDraw,
    *,
    cx0: int,
    cx1: int,
    y: int,
    text: str,
    palette: ContestPalette,
    size: int = 40,
    max_y: int | None = None,
) -> int:
    msg = (text or "").strip()
    if not msg:
        return y
    limit = max_y if max_y is not None else y + 200
    font, lines = fit_font_single_line(
        draw, msg, cx1 - cx0, start_size=size, min_size=max(22, size - 14), bold=True, max_lines=2,
    )
    return draw_centered_lines(
        draw, cx0=cx0, cx1=cx1, y=y, lines=lines, font=font, fill=palette.accent, max_y=limit,
    ) + 10


def draw_contest_speech_bubble(
    draw: ImageDraw.ImageDraw,
    *,
    bx0: int,
    by0: int,
    bx1: int,
    by1: int,
    tail_tip: tuple[int, int],
    tail_from_side: str = "bottom",
) -> None:
    """흰색 라운드 말풍선 + 캐릭터 방향 꼬리."""
    draw_classic_speech_bubble(
        draw,
        bx0=bx0,
        by0=by0,
        bx1=bx1,
        by1=by1,
        tail_tip=tail_tip,
        tail_from_side=tail_from_side,
        fill=BUBBLE_FILL,
        outline=BUBBLE_OUTLINE,
        outline_width=2,
        radius=22,
    )


def draw_section_title(
    draw: ImageDraw.ImageDraw,
    *,
    x0: int,
    y: int,
    accent: str,
    suffix: str,
    palette: ContestPalette,
) -> int:
    bar_w = 6
    font = load_font(38, bold=True)
    accent_text = (accent or "").strip()
    suffix_text = (suffix or "").strip()
    x = x0
    draw.rectangle((x, y + 4, x + bar_w, y + 38), fill=palette.accent)
    x += bar_w + 12
    if accent_text:
        draw.text((x, y), accent_text, font=font, fill=palette.accent)
        x += int(draw.textlength(accent_text, font=font))
    if suffix_text:
        draw.text((x, y), suffix_text, font=font, fill=INK)
    return y + 48


def draw_point_footer(
    draw: ImageDraw.ImageDraw,
    *,
    cx0: int,
    cx1: int,
    cy1: int,
    text: str,
    palette: ContestPalette,
) -> None:
    msg = (text or "").strip()
    if not msg:
        return
    if not msg.upper().startswith("POINT"):
        msg = f"POINT. {msg}"
    font = load_font(32, bold=True)
    lw = int(draw.textlength(msg, font=font))
    cx = cx0 + (cx1 - cx0 - lw) // 2
    draw.text((cx, cy1 - POINT_FOOTER_H + 8), msg, font=font, fill=palette.accent)


def draw_four_point_star(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    size: int,
    fill: tuple[int, int, int],
) -> None:
    s = size
    draw.polygon(
        [
            (cx, cy - s),
            (cx + s // 3, cy - s // 3),
            (cx + s, cy),
            (cx + s // 3, cy + s // 3),
            (cx, cy + s),
            (cx - s // 3, cy + s // 3),
            (cx - s, cy),
            (cx - s // 3, cy - s // 3),
        ],
        fill=fill,
    )


def draw_music_note(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.ellipse((x, y + 18, x + 14, y + 32), fill=NOTE_PINK)
    draw.ellipse((x + 16, y + 10, x + 30, y + 24), fill=NOTE_PINK)
    draw.rectangle((x + 12, y, x + 18, y + 22), fill=NOTE_PINK)
    draw.rectangle((x + 28, y - 8, x + 34, y + 14), fill=NOTE_PINK)


def _bubble_metrics(
    draw: ImageDraw.ImageDraw,
    speech: str,
    max_w: int,
) -> tuple[list[str], int, int, ImageFont.FreeTypeFont]:
    font, lines = fit_font_single_line(
        draw, speech, max_w, start_size=28, min_size=22, bold=True, max_lines=2,
    )
    if not lines:
        return [], 0, 0, font
    pad_x, pad_y = 24, 16
    line_h = line_height(font, GAP_SM)
    bh = pad_y * 2 + line_h * len(lines)
    bw = max((int(draw.textlength(line, font=font)) for line in lines), default=0) + pad_x * 2
    return lines, bw, bh, font


def draw_accent_pill(
    draw: ImageDraw.ImageDraw,
    *,
    cx0: int,
    cx1: int,
    y0: int,
    y1: int,
    text: str,
    palette: ContestPalette,
    start_size: int = 36,
    min_size: int = 28,
) -> bool:
    """텍스트가 있을 때만 CTA/필 버튼 도형을 그림."""
    label = (text or "").strip()
    if not label:
        return False
    font, lines = fit_font_single_line(
        draw, label, cx1 - cx0 - 96, start_size=start_size, min_size=min_size, bold=True, max_lines=2,
    )
    if not lines:
        return False
    lh = measure_text_block(lines, font, line_gap=GAP_SM)
    pad_y = 18
    inner_h = lh + pad_y * 2
    by0 = y1 - inner_h
    if by0 < y0:
        by0 = y0
        inner_h = y1 - by0
    draw.rounded_rectangle((cx0, by0, cx1, y1), radius=26, fill=palette.accent)
    ty = by0 + max(pad_y, (inner_h - lh) // 2)
    draw_centered_lines(
        draw, cx0=cx0 + 12, cx1=cx1 - 12, y=ty, lines=lines,
        font=font, fill=(255, 255, 255), max_y=y1 - 8,
    )
    return True


def paste_mascot_in_zone(
    canvas: Image.Image,
    mascot: Image.Image | None,
    speech: str,
    zone: tuple[int, int, int, int],
    *,
    palette: ContestPalette,
    corner: str = "right",
) -> Image.Image:
    """말풍선(위) → 캐릭터(아래) 순으로 배치, 서로·본문과 겹치지 않음."""
    if mascot is None:
        return canvas
    zx0, zy0, zx1, zy1 = zone
    zone_h = zy1 - zy0
    zone_w = zx1 - zx0
    if zone_h < 140 or zone_w < 120:
        return canvas

    speech = (speech or "").strip()[:14]
    lines: list[str] = []
    bw = bh = 0
    font = load_font(28, bold=True)
    probe = ImageDraw.Draw(Image.new("RGB", (400, 400)))
    if speech:
        lines, bw, bh, font = _bubble_metrics(probe, speech, max(180, zone_w - 56))
    if not lines:
        bw = bh = 0

    pad_x, pad_y = 24, 16
    line_h = line_height(font, GAP_SM) if lines else 0

    icon = mascot.copy()
    max_icon_h = zone_h - bh - SPEECH_ICON_GAP - 24
    max_icon_h = max(100, min(200, max_icon_h))
    icon.thumbnail((int(max_icon_h * 1.15), max_icon_h), Image.Resampling.LANCZOS)

    my = zy1 - icon.height - 12
    if corner == "left":
        mx = zx0 + 16
    else:
        mx = zx1 - icon.width - 16

    base = canvas.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    if lines and bh > 0 and bw > 0:
        by1 = my - SPEECH_ICON_GAP
        by0 = by1 - bh
        if by0 < zy0 + 8:
            by0 = zy0 + 8
            by1 = by0 + bh
            my = min(zy1 - icon.height - 12, by1 + SPEECH_ICON_GAP + icon.height)
            my = max(my, zy0 + bh + SPEECH_ICON_GAP + 8)

        bubble_cx = mx + icon.width // 2
        bx0 = bubble_cx - bw // 2
        bx1 = bx0 + bw
        if bx0 < zx0 + 8:
            shift = zx0 + 8 - bx0
            bx0 += shift
            bx1 += shift
        if bx1 > zx1 - 8:
            shift = bx1 - (zx1 - 8)
            bx0 -= shift
            bx1 -= shift

        tail_x = bubble_cx
        tail_y = my + 8
        draw_contest_speech_bubble(
            draw,
            bx0=bx0,
            by0=by0,
            bx1=bx1,
            by1=by1,
            tail_tip=(tail_x, tail_y),
            tail_from_side="bottom",
        )
        ty = by0 + pad_y
        for line in lines:
            lw = int(draw.textlength(line, font=font))
            tx = bx0 + (bw - lw) // 2
            draw.text((tx, ty), line, font=font, fill=INK)
            ty += line_h

    layer.paste(icon, (mx, my), icon)
    return Image.alpha_composite(base, layer).convert("RGB")


def draw_source_url_footer(
    draw: ImageDraw.ImageDraw,
    *,
    cx0: int,
    cx1: int,
    y: int,
    url: str,
    palette: ContestPalette,
    max_y: int,
) -> None:
    value = (url or "").strip()
    if not value or y >= max_y - 8:
        return
    font = load_font(24)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = wrap_text(probe, value, font, cx1 - cx0 - 32)[:2]
    lh = line_height(font, 6)
    cy = y
    for line in lines:
        if cy + lh > max_y:
            break
        lw = int(draw.textlength(line, font=font))
        tx = cx0 + (cx1 - cx0 - lw) // 2
        draw.text((tx, cy), line, font=font, fill=palette.accent)
        cy += lh


def item_text(item: dict[str, Any]) -> str:
    return str(
        item.get("text") or item.get("value") or item.get("content") or item.get("body") or "",
    ).strip()


def slide_items(slide: dict[str, Any], *, max_items: int = 6) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw in list(slide.get("items") or []):
        if not isinstance(raw, dict):
            continue
        text = item_text(raw)
        if not text:
            continue
        items.append(
            {
                "label": str(raw.get("label") or raw.get("title") or "").strip(),
                "text": text,
            },
        )
    if not items and slide.get("body"):
        items = [{"label": "", "text": t} for t in str(slide["body"]).split("\n") if t.strip()]
    return items[:max_items]


def draw_wrapped_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    x0: int,
    x1: int,
    y: int,
    max_y: int,
    start_size: int = 38,
    min_size: int = 22,
    bold: bool = False,
    fill: tuple[int, int, int] = INK,
    center: bool = False,
    max_lines: int = 12,
) -> int:
    cw = x1 - x0
    available = max_y - y
    if cw < 40 or available < 12:
        return y
    value = (text or "").strip()
    if not value:
        return y

    font = load_font(min_size, bold=bold, extra_bold=bold)
    lines: list[str] = []
    for size in range(start_size, min_size - 1, -2):
        candidate, candidate_lines = fit_font_lines(
            draw,
            value,
            cw,
            start_size=size,
            min_size=size,
            max_lines=max_lines,
            load_font_fn=load_font,
            bold=bold,
            extra_bold=bold,
        )
        block_h = measure_text_block(candidate_lines, candidate, line_gap=GAP_SM)
        if block_h <= available:
            font, lines = candidate, candidate_lines
            break
    if not lines:
        font, lines = fit_font_lines(
            draw,
            value,
            cw,
            start_size=min_size,
            min_size=min_size,
            max_lines=max_lines,
            load_font_fn=load_font,
            bold=bold,
            extra_bold=bold,
        )

    cy = y
    for line in lines:
        lh = line_height(font, GAP_SM)
        if cy + lh > max_y:
            break
        lw = int(draw.textlength(line, font=font))
        tx = x0 + (cw - lw) // 2 if center else x0
        draw.text((tx, cy), line, font=font, fill=fill)
        cy += lh
    return cy
