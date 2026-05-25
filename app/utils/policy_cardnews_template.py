"""정책 카드뉴스 고정 템플릿 (레퍼런스 형식 + 브랜드 #1D87FF + mascots.json 캐릭터)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.utils.policy_cardnews_mascot import (
    BRAND_ACCENT,
    BRAND_BLUE,
    INK_BLACK,
    draw_classic_speech_bubble,
    draw_mascot_narrator,
)
from app.utils.policy_cardnews_visual import paste_rounded_image_fit

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350

LIME_OFFSET = (196, 232, 82)
HIGHLIGHT_GREEN = (196, 232, 82)
INK = (20, 24, 32)
INK_BODY = (52, 60, 78)
GRAY_PANEL = (244, 246, 250)
DOT_GRAY = (200, 208, 220)

CARD_INSET = 36
OFFSET_PX = 12
CONTENT_PAD = 36

DENSITY = 1.08

# 요소·블록 간격
GAP_SECTION = 22
GAP_BLOCK = 16
GAP_LINE_SM = 8
GAP_LINE_MD = 12
GAP_LINE_LG = 16
GAP_MASCOT = 20
GAP_CTA_ABOVE_MASCOT = 36
CTA_MIN_MASCOT_ZONE = 300
GAP_COL = 20
GAP_TILE = 18
GAP_ROW = 14
INSET_PANEL = 22
INSET_TILE = 24

LAYOUT_COVER = "template_cover"
LAYOUT_NUMBERED = "template_numbered"
LAYOUT_THREE_COL = "template_three_col"
LAYOUT_GRID = "template_grid"
LAYOUT_CTA = "template_cta"

# 2×2 그리드는 캐릭터 미사용 (정보 밀도·중앙 정렬 우선)
MASCOT_LAYOUTS = {LAYOUT_COVER, LAYOUT_CTA, LAYOUT_THREE_COL, LAYOUT_NUMBERED}

COVER_MASCOT_MIN_H = 420
COVER_MASCOT_ZONE_RATIO = 0.52
COVER_TEXT_RATIO_WITH_HERO = 0.34

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FONT_DIR = _REPO_ROOT / "app" / "assets" / "fonts"


@dataclass(frozen=True)
class CardFrame:
    outer: tuple[int, int, int, int]
    white: tuple[int, int, int, int]
    content: tuple[int, int, int, int]


@dataclass(frozen=True)
class TemplatePalette:
    name: str
    outer: tuple[int, int, int]
    offset: tuple[int, int, int]
    accent: tuple[int, int, int]


TEMPLATE_PALETTES: dict[str, TemplatePalette] = {
    "royal_blue": TemplatePalette("royal_blue", (29, 135, 255), (196, 232, 82), (29, 135, 255)),
    "coral_sunset": TemplatePalette("coral_sunset", (255, 108, 88), (255, 218, 120), (220, 72, 52)),
    "mint_pop": TemplatePalette("mint_pop", (64, 192, 148), (186, 248, 210), (36, 148, 108)),
    "purple_modern": TemplatePalette("purple_modern", (118, 88, 210), (218, 198, 255), (92, 62, 178)),
    "amber_warm": TemplatePalette("amber_warm", (255, 168, 52), (255, 238, 170), (210, 120, 28)),
    "slate_cool": TemplatePalette("slate_cool", (72, 88, 118), (188, 206, 228), (52, 68, 96)),
    "rose_soft": TemplatePalette("rose_soft", (238, 118, 142), (255, 208, 218), (198, 72, 98)),
    "teal_fresh": TemplatePalette("teal_fresh", (32, 168, 178), (170, 235, 240), (22, 130, 140)),
}

TEMPLATE_PALETTE_NAMES = list(TEMPLATE_PALETTES.keys())

THEME_TO_TEMPLATE_PALETTE: dict[str, str] = {
    "cream_warm": "amber_warm",
    "mint_fresh": "mint_pop",
    "slate_modern": "slate_cool",
    "peach_soft": "coral_sunset",
    "lavender_light": "purple_modern",
    "snow_clean": "royal_blue",
}


@dataclass
class TemplateContext:
    slide: dict[str, Any]
    mascot: Image.Image | None
    slide_no: int
    slide_total: int
    minister: str
    source_url: str
    palette: TemplatePalette
    hero_image: Image.Image | None = None
    use_cover_image: bool = False


def resolve_template_palette(name: str) -> TemplatePalette:
    key = (name or "royal_blue").strip()
    return TEMPLATE_PALETTES.get(key, TEMPLATE_PALETTES["royal_blue"])


DECK_THEME_NAMES = tuple(THEME_TO_TEMPLATE_PALETTE.keys())


def _pick_deck_theme_and_palette(
    slides: list[dict[str, Any]],
    *,
    rng: random.Random,
) -> tuple[str, str]:
    """카드뉴스 1건(주제)에 쓸 theme·template_palette 한 세트."""
    deck_theme = ""
    for slide in slides:
        candidate = str(slide.get("theme") or "").strip()
        if candidate in THEME_TO_TEMPLATE_PALETTE:
            deck_theme = candidate
            break

    if deck_theme:
        palette = THEME_TO_TEMPLATE_PALETTE[deck_theme]
        if palette in TEMPLATE_PALETTES:
            return deck_theme, palette

    palette = str(slides[0].get("template_palette") if slides else "").strip()
    if palette not in TEMPLATE_PALETTES:
        palette = rng.choice(TEMPLATE_PALETTE_NAMES)
    deck_theme = deck_theme or next(
        (t for t, p in THEME_TO_TEMPLATE_PALETTE.items() if p == palette),
        rng.choice(DECK_THEME_NAMES),
    )
    return deck_theme, palette


def apply_deck_template_theme(
    slides: list[dict[str, Any]],
    *,
    rng: random.Random,
    contentid: str = "",
) -> list[dict[str, Any]]:
    """한 주제(카드뉴스) 안 모든 슬라이드에 동일 theme·palette."""
    deck_rng = random.Random(contentid) if contentid else rng
    deck_theme, deck_palette = _pick_deck_theme_and_palette(slides, rng=deck_rng)
    out: list[dict[str, Any]] = []
    for slide in slides:
        row = dict(slide)
        row["theme"] = deck_theme
        row["template_palette"] = deck_palette
        out.append(row)
    return out


def diversify_template_palettes(slides: list[dict[str, Any]], *, rng: random.Random) -> list[dict[str, Any]]:
    """하위 호환: 슬라이드마다가 아니라 덱 단위 통일."""
    return apply_deck_template_theme(slides, rng=rng)


def _cover_uses_hero(ctx: TemplateContext) -> bool:
    return ctx.use_cover_image and ctx.hero_image is not None


def _load_font(size: int, *, bold: bool = False, extra_bold: bool = False) -> ImageFont.FreeTypeFont:
    size = max(18, int(size))
    if extra_bold:
        names = ["Pretendard-ExtraBold.otf", "Pretendard-ExtraBold.ttf", "Pretendard-Bold.otf"]
    elif bold:
        names = ["Pretendard-Bold.otf", "Pretendard-Bold.ttf", "Pretendard-SemiBold.otf"]
    else:
        names = ["Pretendard-Medium.otf", "Pretendard-Regular.otf"]
    for name in names:
        path = _FONT_DIR / name
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _line_height(font: ImageFont.FreeTypeFont, gap: int = 0) -> int:
    a, d = font.getmetrics()
    return a + d + gap


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
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


def _fit_font_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_w: int,
    *,
    start_size: int,
    min_size: int,
    max_lines: int,
    bold: bool = False,
    extra_bold: bool = False,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    value = (text or "").strip()
    if not value:
        font = _load_font(min_size, bold=bold, extra_bold=extra_bold)
        return font, []
    for size in range(start_size, min_size - 1, -2):
        font = _load_font(size, bold=bold, extra_bold=extra_bold)
        lines = _wrap(draw, value, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
    font = _load_font(min_size, bold=bold, extra_bold=extra_bold)
    return font, _wrap(draw, value, font, max_w)[:max_lines]


def _measure_text_block(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    *,
    line_gap: int,
) -> int:
    if not lines:
        return 0
    return len(lines) * _line_height(font, line_gap) - line_gap


def _fill_scale(used_h: int, available_h: int, *, min_scale: float = 1.08, max_scale: float = 1.78) -> float:
    """남는 세로 공간이 많을수록 글자·요소를 키움."""
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


def _scaled_size(base: int, scale: float, *, min_size: int = 18, max_size: int = 112) -> int:
    return max(min_size, min(max_size, int(base * DENSITY * scale)))


def _fit_text_in_rect(
    draw: ImageDraw.ImageDraw,
    text: str,
    inner_w: int,
    inner_h: int,
    *,
    start_size: int,
    min_size: int,
    line_gap: int = GAP_LINE_MD,
    bold: bool = False,
    extra_bold: bool = False,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """사각 영역 안에 들어가도록 글자 크기·줄 수 조절."""
    value = (text or "").strip()
    if not value or inner_h < 16 or inner_w < 32:
        return _load_font(min_size, bold=bold, extra_bold=extra_bold), []

    for size in range(start_size, min_size - 1, -2):
        font = _load_font(size, bold=bold, extra_bold=extra_bold)
        lines = _wrap(draw, value, font, inner_w)
        lh = _line_height(font, line_gap)
        max_lines = max(1, inner_h // max(lh, 1))
        clipped = lines[:max_lines]
        if len(lines) <= max_lines:
            block_h = _measure_text_block(draw, clipped, font, line_gap=line_gap)
            if block_h <= inner_h:
                return font, clipped

    font = _load_font(min_size, bold=bold, extra_bold=extra_bold)
    lines = _wrap(draw, value, font, inner_w)
    lh = _line_height(font, line_gap)
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
        cy += _line_height(font, line_gap)
    return cy


MIN_MASCOT_ZONE_H = 220


def _content_and_mascot_bounds(
    cy0: int,
    cy1: int,
    has_mascot: bool,
    *,
    text_end: int | None = None,
) -> tuple[int, int, int, int]:
    """본문 하한·캐릭터 영역을 분리해 겹침 방지. (content_top, content_bottom, mascot_top, mascot_bottom)"""
    content_top = cy0
    mascot_bottom = cy1 - CONTENT_PAD // 2
    if not has_mascot:
        return content_top, mascot_bottom, mascot_bottom, mascot_bottom

    zone_h = max(MIN_MASCOT_ZONE_H, int((cy1 - cy0) * 0.34))
    mascot_top = mascot_bottom - zone_h
    if text_end is not None:
        needed_top = text_end + GAP_MASCOT
        if needed_top > mascot_top:
            mascot_top = min(needed_top, mascot_bottom - 160)
    content_bottom = mascot_top - GAP_MASCOT
    content_bottom = max(content_top + 80, content_bottom)
    return content_top, content_bottom, mascot_top, mascot_bottom


def _center_block_x(block_w: int, cx0: int, cx1: int) -> int:
    return cx0 + max(0, (cx1 - cx0 - block_w) // 2)


def _layout_center_mascot_block(
    mascot: Image.Image,
    speech: str,
    zone_h: int,
    *,
    cx0: int,
    cx1: int,
) -> tuple[Image.Image, ImageFont.FreeTypeFont, list[str], int, int, int, int, int, int]:
    """말풍선+캐릭터를 zone_h 스트립 좌표(0~zone_h)에 배치."""
    speech = (speech or "").strip()[:18]
    max_h = max(380, int(zone_h * 0.98))
    font_size = _scaled_size(36, _fill_scale(50, zone_h, max_scale=1.55), min_size=30, max_size=44)
    font = _load_font(font_size, bold=True)
    icon = mascot.copy()
    icon_max = min(max_h, max(100, int(zone_h * 0.58)))
    icon.thumbnail((int(icon_max * 1.1), icon_max), Image.Resampling.LANCZOS)
    mx = (CANVAS_WIDTH - icon.width) // 2

    speech_gap = 18
    pad_x, pad_y = 32, 22
    line_h = int(font.size * 1.28)
    bubble_max_w = min(460, cx1 - cx0 - 56)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = _wrap(probe, speech, font, bubble_max_w - 72)[:2] if speech else []
    bh = pad_y * 2 + line_h * len(lines) if lines else 0
    block_h = icon.height + (bh + speech_gap if lines else 0) + GAP_BLOCK * 2
    if block_h > zone_h:
        shrink = max(0.5, zone_h / block_h)
        icon_max = max(90, int(icon_max * shrink))
        icon.thumbnail((int(icon_max * 1.1), icon_max), Image.Resampling.LANCZOS)
        font_size = max(22, int(font_size * shrink))
        font = _load_font(font_size, bold=True)
        line_h = int(font.size * 1.28)
        lines = _wrap(probe, speech, font, bubble_max_w - 72)[:2] if speech else []
        bh = pad_y * 2 + line_h * len(lines) if lines else 0

    my = zone_h - icon.height - GAP_BLOCK
    by0, by1 = GAP_BLOCK, GAP_BLOCK + bh
    if lines:
        by1 = my - speech_gap
        by0 = max(GAP_BLOCK, by1 - bh)
        if by0 <= GAP_BLOCK and by1 + speech_gap + icon.height > zone_h - GAP_BLOCK:
            my = zone_h - icon.height - GAP_BLOCK
            by1 = max(GAP_BLOCK + bh, my - speech_gap)
            by0 = max(GAP_BLOCK, by1 - bh)
    return icon, font, lines, mx, my, by0, by1, pad_x, pad_y, line_h


def _estimate_cta_mascot_zone_height(
    mascot: Image.Image,
    speech: str,
    *,
    cx0: int,
    cx1: int,
    zone_bottom: int,
    zone_top_limit: int,
) -> int:
    """캐릭터+말풍선이 들어갈 최소 세로 높이 (_layout_center_mascot_block과 동일)."""
    strip_cap = zone_bottom - zone_top_limit
    probe_h = max(CTA_MIN_MASCOT_ZONE, min(560, strip_cap))
    icon, _font, lines, _mx, my, by0, _by1, _px, _py, _lh = _layout_center_mascot_block(
        mascot, speech, probe_h, cx0=cx0, cx1=cx1
    )
    top = by0 if lines else my
    used = probe_h - top + GAP_BLOCK
    return max(CTA_MIN_MASCOT_ZONE, min(int(used), strip_cap))


def _cta_content_bounds(cy0: int, cy1: int, has_mascot: bool) -> tuple[int, int, int, int]:
    """마무리: 캐릭터 영역을 넉넉히."""
    mascot_bottom = cy1 - CONTENT_PAD // 2
    if not has_mascot:
        return cy0, mascot_bottom, mascot_bottom, mascot_bottom
    zone_h = max(280, int((cy1 - cy0) * 0.40))
    mascot_top = mascot_bottom - zone_h
    content_bottom = mascot_top - GAP_MASCOT
    return cy0, content_bottom, mascot_top, mascot_bottom


def _draw_term_guide_panel(
    draw: ImageDraw.ImageDraw,
    *,
    cx0: int,
    cx1: int,
    y: int,
    guides: list[str],
    bottom_limit: int,
) -> int:
    """쉬운 말 설명란."""
    lines = [g.strip() for g in guides if g.strip()][:2]
    if not lines or y >= bottom_limit - 60:
        return y

    pad_x = INSET_PANEL
    inner_w = cx1 - cx0 - pad_x * 2
    title_f = _load_font(22, bold=True)
    body_f = _load_font(20)
    title_h = _line_height(title_f, GAP_LINE_SM)
    body_lines: list[str] = []
    for line in lines:
        body_lines.extend(_wrap(draw, line, body_f, inner_w)[:2])
    body_lines = body_lines[:3]
    panel_h = (
        pad_x
        + title_h
        + GAP_LINE_SM
        + _measure_text_block(draw, body_lines, body_f, line_gap=GAP_LINE_SM)
        + pad_x
    )
    panel_h = min(panel_h, max(80, bottom_limit - y - GAP_BLOCK))
    px0 = cx0 + pad_x
    px1 = cx1 - pad_x
    py0 = y
    py1 = min(bottom_limit - GAP_BLOCK, py0 + panel_h)
    draw.rounded_rectangle((px0, py0, px1, py1), radius=12, fill=GRAY_PANEL)
    ty = py0 + pad_x // 2
    title = "쉬운 말로"
    draw.text((px0 + pad_x, ty), title, font=title_f, fill=INK)
    ty += title_h + GAP_LINE_SM
    for line in body_lines:
        draw.text((px0 + pad_x, ty), line, font=body_f, fill=INK_BODY)
        ty += _line_height(body_f, GAP_LINE_SM)
    return py1 + GAP_SECTION


def _draw_cta_action_panel(
    draw: ImageDraw.ImageDraw,
    *,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
    label: str,
    palette: TemplatePalette,
) -> None:
    """그리드 타일 리본과 동일한 톤의 원문 CTA 버튼."""
    draw.rounded_rectangle((x0, y0, x1, y1), radius=14, fill=palette.accent)
    inner_h = y1 - y0
    font, lines = _fit_font_lines(
        draw,
        label,
        x1 - x0 - INSET_PANEL * 2,
        start_size=40,
        min_size=28,
        max_lines=2,
        bold=True,
    )
    block_h = _measure_text_block(draw, lines, font, line_gap=GAP_LINE_SM)
    ty = y0 + max(INSET_PANEL // 2, (inner_h - block_h) // 2)
    for line in lines:
        lw = int(draw.textlength(line, font=font))
        draw.text((x0 + (x1 - x0 - lw) // 2, ty), line, font=font, fill=BRAND_ACCENT)
        ty += _line_height(font, GAP_LINE_SM)


def _cover_mascot_bounds(
    cy0: int, cy1: int, text_end: int | None = None
) -> tuple[int, int, int]:
    """표지: 캐릭터 영역을 크게 확보. (text_bottom, mascot_top, mascot_bottom)"""
    mascot_bottom = cy1 - CONTENT_PAD // 2
    zone_h = max(COVER_MASCOT_MIN_H, int((cy1 - cy0) * COVER_MASCOT_ZONE_RATIO))
    mascot_top = mascot_bottom - zone_h
    if text_end is not None:
        mascot_top = max(mascot_top, text_end + GAP_MASCOT)
    min_top = mascot_bottom - COVER_MASCOT_MIN_H
    mascot_top = min(mascot_top, min_top)
    text_bottom = mascot_top - GAP_MASCOT
    return max(cy0 + 60, text_bottom), mascot_top, mascot_bottom


def _slide_items(slide: dict[str, Any]) -> list[dict[str, str]]:
    items = [i for i in list(slide.get("items") or []) if str(i.get("text") or "").strip()]
    if not items and slide.get("body"):
        items = [{"label": "", "text": t} for t in str(slide["body"]).split("\n") if t.strip()]
    return items[:6]


def _card_frame() -> CardFrame:
    wx0 = CARD_INSET
    wy0 = CARD_INSET
    wx1 = CANVAS_WIDTH - CARD_INSET
    wy1 = CANVAS_HEIGHT - CARD_INSET
    white = (wx0, wy0, wx1, wy1)
    content = (wx0 + CONTENT_PAD, wy0 + CONTENT_PAD, wx1 - CONTENT_PAD, wy1 - CONTENT_PAD)
    return CardFrame(outer=(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT), white=white, content=content)


def _draw_frame_base(palette: TemplatePalette) -> Image.Image:
    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), palette.outer)
    frame = _card_frame()
    draw = ImageDraw.Draw(canvas)
    gx0, gy0, gx1, gy1 = frame.white
    draw.rectangle(
        (gx0 + OFFSET_PX, gy0 + OFFSET_PX, gx1 + OFFSET_PX, gy1 + OFFSET_PX),
        fill=palette.offset,
    )
    draw.rectangle(frame.white, fill=(255, 255, 255))
    return canvas


def _draw_highlighter_title(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    text: str,
    max_w: int,
    font: ImageFont.FreeTypeFont,
    line_gap: int = GAP_LINE_MD,
) -> int:
    lines = _wrap(draw, text, font, max_w)
    cy = y
    for line in lines[:3]:
        lw = int(draw.textlength(line, font=font))
        lx = x + (max_w - lw) // 2
        draw.rectangle(
            (lx - 8, cy + 6, lx + lw + 8, cy + _line_height(font, 4)),
            fill=HIGHLIGHT_GREEN,
        )
        draw.text((lx, cy), line, font=font, fill=INK)
        cy += _line_height(font, line_gap)
    return cy


def _paste_mascot_zone(
    canvas: Image.Image,
    mascot: Image.Image | None,
    speech: str,
    *,
    zone_top: int,
    zone_bottom: int,
    align: str = "left",
) -> Image.Image:
    if mascot is None:
        return canvas
    zone_h = zone_bottom - zone_top
    large_center = align == "center"
    max_h = max(380 if large_center else 280, int(zone_h * (0.98 if large_center else 0.92)))
    font_size = _scaled_size(36, _fill_scale(50, zone_h, max_scale=1.55), min_size=30, max_size=44)
    font = _load_font(font_size, bold=True)
    frame = _card_frame()
    content_x0, _, content_x1, _ = frame.content

    if align == "left":
        return draw_mascot_narrator(
            canvas,
            mascot,
            speech,
            font=font,
            strip_top=zone_top,
            strip_bottom=zone_bottom,
            text_fill=INK_BLACK,
            mascot_max_height=max_h,
            margin=content_x0,
            gap=26,
            center_in_strip=True,
            strip_x0=content_x0,
            strip_x1=content_x1,
        )

    icon, font, lines, mx, my, by0, by1, pad_x, pad_y, line_h = _layout_center_mascot_block(
        mascot, speech, zone_h, cx0=content_x0, cx1=content_x1
    )
    strip = Image.new("RGBA", (CANVAS_WIDTH, zone_h), (0, 0, 0, 0))
    if lines:
        draw = ImageDraw.Draw(strip)
        bw = max(int(draw.textlength(line, font=font)) for line in lines) + pad_x * 2
        bx0 = _center_block_x(bw, content_x0, content_x1)
        tail_tip = (mx + icon.width // 2, min(my + 4, zone_h - GAP_BLOCK))
        shadow = Image.new("RGBA", strip.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        sdraw.rounded_rectangle((bx0 + 4, by0 + 6, bx0 + bw + 4, by1 + 6), radius=28, fill=(0, 0, 0, 50))
        strip = Image.alpha_composite(strip, shadow)
        draw = ImageDraw.Draw(strip)
        draw_classic_speech_bubble(
            draw,
            bx0=bx0,
            by0=by0,
            bx1=bx0 + bw,
            by1=by1,
            tail_tip=tail_tip,
            tail_from_side="bottom",
        )
        ty = by0 + pad_y
        for line in lines:
            draw.text((bx0 + pad_x, ty), line, font=font, fill=INK_BLACK)
            ty += line_h
    strip.paste(icon, (mx, my), icon)
    base = canvas.convert("RGBA")
    base.paste(strip, (0, zone_top), strip)
    return base


def render_template_cover(ctx: TemplateContext) -> Image.Image:
    slide = ctx.slide
    palette = ctx.palette
    use_hero = _cover_uses_hero(ctx)
    canvas = _draw_frame_base(palette)
    draw = ImageDraw.Draw(canvas)
    frame = _card_frame()
    cx0, cy0, cx1, cy1 = frame.content
    cw = cx1 - cx0
    cx = (cx0 + cx1) // 2

    eyebrow = str(slide.get("eyebrow") or slide.get("subtext") or "").strip()
    headline = str(slide.get("headline") or "").strip()
    highlight = str(slide.get("highlight") or "").strip()
    speech = str(slide.get("speech") or "").strip()

    has_mascot = ctx.mascot is not None and not use_hero
    mascot_top = mascot_bottom = cy1
    if use_hero:
        text_bottom = cy0 + int((cy1 - cy0) * COVER_TEXT_RATIO_WITH_HERO)
    elif has_mascot:
        text_bottom, mascot_top, mascot_bottom = _cover_mascot_bounds(cy0, cy1)
    else:
        text_bottom = cy1 - CONTENT_PAD // 2
    text_available = text_bottom - cy0

    parts: list[tuple[str, str]] = []
    if eyebrow:
        parts.append(("eyebrow", eyebrow))
    if headline:
        parts.append(("headline", headline))
    if highlight and highlight != headline:
        parts.append(("highlight", highlight))

    base_used = 0
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for kind, text in parts:
        if kind == "eyebrow":
            f, lines = _fit_font_lines(probe, text, cw - 24, start_size=34, min_size=26, max_lines=2, bold=True)
        elif kind == "headline":
            f, lines = _fit_font_lines(probe, text, cw - 32, start_size=80, min_size=52, max_lines=2, extra_bold=True)
        else:
            f, lines = _fit_font_lines(probe, text, cw - 32, start_size=76, min_size=48, max_lines=2, extra_bold=True)
        base_used += _measure_text_block(probe, lines, f, line_gap=GAP_LINE_SM) + GAP_BLOCK

    scale = _fill_scale(base_used, text_available)
    y = cy0 + max(GAP_BLOCK, int((text_available - base_used * scale) * 0.10))

    for kind, text in parts:
        if kind == "eyebrow":
            font, lines = _fit_font_lines(
                draw,
                text,
                cw - 32,
                start_size=_scaled_size(34, scale),
                min_size=26,
                max_lines=2,
                bold=True,
            )
            for line in lines:
                lh = _line_height(font, GAP_LINE_SM)
                if has_mascot and y + lh > text_bottom:
                    break
                lw = int(draw.textlength(line, font=font))
                draw.text((cx - lw // 2, y), line, font=font, fill=INK_BODY)
                y += lh
            y += GAP_LINE_LG
        elif kind == "headline":
            font, lines = _fit_font_lines(
                draw,
                text,
                cw - 40,
                start_size=_scaled_size(80, scale),
                min_size=52,
                max_lines=2,
                extra_bold=True,
            )
            for line in lines:
                lh = _line_height(font, GAP_LINE_MD)
                if has_mascot and y + lh > text_bottom:
                    break
                lw = int(draw.textlength(line, font=font))
                draw.text((cx - lw // 2, y), line, font=font, fill=INK)
                y += lh
            y += GAP_LINE_LG
        else:
            font, lines = _fit_font_lines(
                draw,
                text,
                cw - 40,
                start_size=_scaled_size(76, scale),
                min_size=48,
                max_lines=2,
                extra_bold=True,
            )
            for line in lines:
                tape_h = _line_height(font, 6) + 14
                if has_mascot and y + tape_h > text_bottom:
                    break
                lw = int(draw.textlength(line, font=font))
                draw.rounded_rectangle(
                    (cx - lw // 2 - 18, y, cx + lw // 2 + 18, y + tape_h), radius=8, fill=palette.accent
                )
                draw.text((cx - lw // 2, y + 5), line, font=font, fill=BRAND_ACCENT)
                y += tape_h + GAP_LINE_LG

    if use_hero and ctx.hero_image is not None:
        img_y0 = y + GAP_SECTION
        img_y1 = cy1 - CONTENT_PAD // 2
        img_box = (cx0 + INSET_PANEL, img_y0, cx1 - INSET_PANEL, img_y1)
        canvas = paste_rounded_image_fit(canvas, ctx.hero_image, box=img_box, radius=28)
        return canvas.convert("RGB")

    if has_mascot:
        _, mascot_top, mascot_bottom = _cover_mascot_bounds(cy0, cy1, text_end=y)
        return _paste_mascot_zone(
            canvas, ctx.mascot, speech, zone_top=mascot_top, zone_bottom=mascot_bottom, align="center"
        )
    return canvas.convert("RGB")


def _render_header(
    draw: ImageDraw.ImageDraw,
    *,
    frame: CardFrame,
    eyebrow: str,
    headline: str,
    bottom_limit: int,
) -> int:
    cx0, cy0, cx1, _ = frame.content
    cw = cx1 - cx0
    available = bottom_limit - cy0
    y = cy0 + GAP_BLOCK

    if eyebrow:
        font, lines = _fit_font_lines(
            draw,
            eyebrow,
            cw - 24,
            start_size=_scaled_size(32, _fill_scale(36, available)),
            min_size=24,
            max_lines=2,
            bold=True,
        )
        for line in lines:
            lh = _line_height(font, GAP_LINE_MD) + 8
            if y + lh > bottom_limit - GAP_BLOCK:
                break
            y = _draw_highlighter_title(draw, x=cx0, y=y, text=line, max_w=cw, font=font, line_gap=GAP_LINE_MD)
        y += GAP_LINE_MD

    if headline:
        font, lines = _fit_font_lines(
            draw,
            headline,
            cw - 16,
            start_size=_scaled_size(52, _fill_scale(72, available)),
            min_size=36,
            max_lines=2,
            extra_bold=True,
        )
        for line in lines:
            lh = _line_height(font, GAP_LINE_LG) + 8
            if y + lh > bottom_limit - GAP_BLOCK:
                break
            y = _draw_highlighter_title(draw, x=cx0, y=y, text=line, max_w=cw, font=font, line_gap=GAP_LINE_LG)

    return min(y + GAP_SECTION, bottom_limit)


def render_template_numbered(ctx: TemplateContext) -> Image.Image:
    slide = ctx.slide
    palette = ctx.palette
    canvas = _draw_frame_base(palette)
    draw = ImageDraw.Draw(canvas)
    frame = _card_frame()
    cx0, cy0, cx1, cy1 = frame.content
    cw = cx1 - cx0

    items = _slide_items(slide)[:4]
    has_mascot = ctx.mascot is not None and len(items) <= 3
    _, body_bottom, mascot_top, mascot_bottom = _content_and_mascot_bounds(cy0, cy1, has_mascot)

    eyebrow = str(slide.get("eyebrow") or "한 장 요약").strip()
    headline = str(slide.get("headline") or "").strip()
    y = _render_header(draw, frame=frame, eyebrow=eyebrow, headline=headline, bottom_limit=body_bottom)

    n = max(len(items), 1)
    body_h = body_bottom - y
    row_h = max(48, (body_h - GAP_ROW * max(0, n - 1)) // n)
    scale = _fill_scale(64 * n, body_h, max_scale=1.65)

    title_size = _scaled_size(36, scale, min_size=28, max_size=48)
    title_f = _load_font(title_size, bold=True)

    for index, item in enumerate(items):
        row_y0 = y + index * (row_h + GAP_ROW)
        row_y1 = min(body_bottom, row_y0 + row_h)
        if row_y0 >= body_bottom - GAP_BLOCK:
            break
        inner_h = row_y1 - row_y0
        label = str(item.get("label") or "").strip()
        text = str(item.get("text") or "").strip()
        row_title = f"{label} · {text}".strip(" ·") if label else text

        num_size = _scaled_size(30, scale, min_size=24, max_size=38)
        num_r = max(26, int(inner_h * 0.26))
        num_x = cx0 + INSET_PANEL // 2
        num_y = row_y0 + (inner_h - num_r * 2) // 2
        draw.ellipse((num_x, num_y, num_x + num_r * 2, num_y + num_r * 2), fill=palette.accent)
        nf = _load_font(num_size, bold=True)
        num_t = f"{index + 1}"
        nw = int(draw.textlength(num_t, font=nf))
        draw.text((num_x + num_r - nw // 2, num_y + num_r - _line_height(nf, 0) // 2), num_t, font=nf, fill=BRAND_ACCENT)

        text_x0 = cx0 + num_r * 2 + GAP_SECTION
        text_x1 = cx1 - INSET_PANEL
        text_w = text_x1 - text_x0
        wrapped = _wrap(draw, row_title, title_f, text_w)[:3]
        block_h = _measure_text_block(draw, wrapped, title_f, line_gap=GAP_LINE_MD)
        ty = row_y0 + max(GAP_BLOCK, (inner_h - block_h) // 2)
        for line in wrapped:
            lw = int(draw.textlength(line, font=title_f))
            draw.text((text_x0 + (text_w - lw) // 2, ty), line, font=title_f, fill=INK)
            ty += _line_height(title_f, GAP_LINE_MD)

        if index < len(items) - 1:
            sep_y = row_y1 + GAP_ROW // 2
            draw.line([(cx0 + 56, sep_y), (cx1 - INSET_PANEL, sep_y)], fill=DOT_GRAY, width=2)

    if has_mascot:
        return _paste_mascot_zone(
            canvas,
            ctx.mascot,
            str(slide.get("speech") or "핵심만!")[:18],
            zone_top=mascot_top,
            zone_bottom=mascot_bottom,
            align="left",
        )
    return canvas.convert("RGB")


def render_template_three_col(ctx: TemplateContext) -> Image.Image:
    slide = ctx.slide
    palette = ctx.palette
    canvas = _draw_frame_base(palette)
    draw = ImageDraw.Draw(canvas)
    frame = _card_frame()
    cx0, cy0, cx1, cy1 = frame.content
    cw = cx1 - cx0

    items = _slide_items(slide)[:3]
    has_mascot = ctx.mascot is not None
    _, body_bottom, mascot_top, mascot_bottom = _content_and_mascot_bounds(cy0, cy1, has_mascot)

    eyebrow = str(slide.get("eyebrow") or "").strip()
    headline = str(slide.get("headline") or "핵심만 정리").strip()
    y = _render_header(draw, frame=frame, eyebrow=eyebrow, headline=headline, bottom_limit=body_bottom)

    col_gap = GAP_COL
    n_cols = max(len(items), 1)
    col_w = (cw - col_gap * (n_cols - 1)) // n_cols
    grid_w = n_cols * col_w + col_gap * (n_cols - 1)
    grid_x0 = _center_block_x(grid_w, cx0, cx1)
    col_top = y + GAP_BLOCK
    col_bottom = body_bottom
    col_h = col_bottom - col_top

    for col_index, item in enumerate(items):
        col_x0 = grid_x0 + col_index * (col_w + col_gap)
        draw.rounded_rectangle((col_x0, col_top, col_x0 + col_w, col_bottom), radius=14, fill=GRAY_PANEL)
        pad = INSET_PANEL
        inner_w = col_w - pad * 2

        label = str(item.get("label") or f"항목{col_index + 1}").strip()
        text = str(item.get("text") or "").strip()

        badge = max(44, min(56, int(col_h * 0.13)))
        badge_y = col_top + pad
        cx_center = col_x0 + col_w // 2
        draw.ellipse(
            (cx_center - badge // 2, badge_y, cx_center + badge // 2, badge_y + badge),
            fill=palette.accent,
        )
        nf = _load_font(_scaled_size(22, 1.0), bold=True)
        num = f"{col_index + 1:02d}"
        nw = int(draw.textlength(num, font=nf))
        draw.text((cx_center - nw // 2, badge_y + badge // 4), num, font=nf, fill=BRAND_ACCENT)

        label_h = max(36, int(col_h * 0.18))
        label_font, label_lines = _fit_text_in_rect(
            draw, label, inner_w, label_h, start_size=32, min_size=24, line_gap=GAP_LINE_SM, bold=True
        )
        ly = badge_y + badge + GAP_LINE_MD
        _draw_centered_lines(
            draw, lines=label_lines, font=label_font, x0=col_x0 + pad, width=inner_w, y=ly, fill=INK, line_gap=GAP_LINE_SM
        )

        content_top = ly + label_h + GAP_LINE_SM
        content_h = max(40, col_bottom - content_top - pad)
        body_font, body_lines = _fit_text_in_rect(
            draw, text, inner_w, content_h, start_size=30, min_size=22, line_gap=GAP_LINE_MD
        )
        body_block_h = _measure_text_block(draw, body_lines, body_font, line_gap=GAP_LINE_MD)
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
        return _paste_mascot_zone(
            canvas,
            ctx.mascot,
            str(slide.get("speech") or "핵심포인트!")[:18],
            zone_top=mascot_top,
            zone_bottom=mascot_bottom,
            align="left",
        )
    return canvas.convert("RGB")


def render_template_grid(ctx: TemplateContext) -> Image.Image:
    slide = ctx.slide
    palette = ctx.palette
    canvas = _draw_frame_base(palette)
    draw = ImageDraw.Draw(canvas)
    frame = _card_frame()
    cx0, cy0, cx1, cy1 = frame.content
    cw = cx1 - cx0

    items = _slide_items(slide)[:4]
    body_bottom = cy1 - CONTENT_PAD // 2

    eyebrow = str(slide.get("eyebrow") or "").strip()
    headline = str(slide.get("headline") or "이렇게 확인하세요").strip()
    y = _render_header(draw, frame=frame, eyebrow=eyebrow, headline=headline, bottom_limit=body_bottom)

    gap = GAP_TILE
    tile_w = (cw - gap) // 2
    rows = 2
    grid_h = body_bottom - y
    tile_h = max(120, (grid_h - gap) // rows)
    grid_total_h = tile_h * rows + gap
    grid_y0 = y + max(0, (grid_h - grid_total_h) // 2)
    grid_w = tile_w * 2 + gap
    grid_x0 = _center_block_x(grid_w, cx0, cx1)
    tile_pad = INSET_TILE

    for index, item in enumerate(items):
        col = index % 2
        row = index // 2
        tx0 = grid_x0 + col * (tile_w + gap)
        ty0 = grid_y0 + row * (tile_h + gap)
        tx1 = tx0 + tile_w
        ty1 = min(body_bottom, ty0 + tile_h)
        draw.rounded_rectangle((tx0, ty0, tx1, ty1), radius=14, fill=GRAY_PANEL)

        label = str(item.get("label") or f"포인트{index + 1}").strip()
        text = str(item.get("text") or "").strip()
        inner_x0 = tx0 + tile_pad
        inner_x1 = tx1 - tile_pad
        inner_w = inner_x1 - inner_x0

        ribbon_h = max(52, int((ty1 - ty0) * 0.28))
        draw.rectangle((tx0, ty0, tx1, ty0 + ribbon_h), fill=palette.accent)

        label_font, label_lines = _fit_text_in_rect(
            draw,
            label,
            inner_w,
            ribbon_h - tile_pad,
            start_size=42,
            min_size=30,
            line_gap=GAP_LINE_SM,
            bold=True,
        )
        label_block_h = _measure_text_block(draw, label_lines, label_font, line_gap=GAP_LINE_SM)
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
            start_size=44,
            min_size=30,
            line_gap=GAP_LINE_MD,
        )
        body_block_h = _measure_text_block(draw, body_lines, body_font, line_gap=GAP_LINE_MD)
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


def render_template_cta(ctx: TemplateContext) -> Image.Image:
    slide = ctx.slide
    palette = ctx.palette
    canvas = _draw_frame_base(palette)
    draw = ImageDraw.Draw(canvas)
    frame = _card_frame()
    cx0, cy0, cx1, cy1 = frame.content
    cw = cx1 - cx0

    eyebrow = str(slide.get("eyebrow") or "마무리").strip()
    headline = str(slide.get("headline") or "자세한 내용은 원문에서").strip()
    cta = str(slide.get("cta") or "원문 뉴스 보기").strip()
    body = str(slide.get("body") or "").strip()
    speech = str(slide.get("speech") or "").strip()
    if not speech:
        speech = "궁금하면 원문 봐!"
    speech = speech[:18]
    term_guides = [str(g).strip() for g in list(slide.get("term_guides") or []) if str(g).strip()]

    has_mascot = ctx.mascot is not None
    mascot_bottom = cy1 - CONTENT_PAD // 2
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
        content_limit = mascot_top - GAP_CTA_ABOVE_MASCOT

    available = max(120, content_limit - cy0)
    scale = _fill_scale(180, available, max_scale=1.48)

    panel_x0 = cx0 + INSET_PANEL
    panel_x1 = cx1 - INSET_PANEL
    box_h = _scaled_size(96, scale, min_size=76, max_size=108)
    uf = _load_font(_scaled_size(20, scale, min_size=18))
    url_line_h = _line_height(uf, GAP_LINE_SM)
    url = (ctx.source_url or "").strip()
    url_block_h = url_line_h + (GAP_LINE_LG if url else 0)

    term_block_h = 0
    if term_guides:
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        tf = _load_font(22, bold=True)
        bf = _load_font(20)
        for g in term_guides[:2]:
            term_block_h += _line_height(tf, GAP_LINE_SM) + _measure_text_block(
                probe, _wrap(probe, g, bf, cw - INSET_PANEL * 4)[:2], bf, line_gap=GAP_LINE_SM
            )
        term_block_h += INSET_PANEL + GAP_SECTION

    body_block_h = 0
    small = _load_font(_scaled_size(24, scale, min_size=20))
    if body:
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        blines = _wrap(probe, body, small, cw - 56)[:2]
        body_block_h = _measure_text_block(probe, blines, small, line_gap=GAP_LINE_SM) + GAP_SECTION

    # 아래에서 위로: URL → CTA박스 → (본문·용어) → 제목 (위치 확정 후 상단 텍스트 배치)
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
    y = _render_header(
        draw,
        frame=frame,
        eyebrow=eyebrow,
        headline=headline,
        bottom_limit=y_max_for_titles,
    )

    if term_guides and y < y_max_for_titles:
        y = _draw_term_guide_panel(
            draw,
            cx0=cx0,
            cx1=cx1,
            y=y,
            guides=term_guides,
            bottom_limit=min(y_max_for_titles, box_y0 - GAP_BLOCK),
        )

    if body and y < box_y0 - GAP_BLOCK:
        blines = _wrap(draw, body, small, panel_x1 - panel_x0 - INSET_PANEL)[:2]
        for line in blines:
            if y + _line_height(small, GAP_LINE_SM) > box_y0 - GAP_BLOCK:
                break
            draw.text((panel_x0, y), line, font=small, fill=INK_BODY)
            y += _line_height(small, GAP_LINE_SM)

    if y < box_y0 - GAP_SECTION:
        sep_y = box_y0 - GAP_SECTION // 2
        draw.line([(panel_x0, sep_y), (panel_x1, sep_y)], fill=DOT_GRAY, width=2)

    cta_label = cta or "원문 뉴스 보기"
    _draw_cta_action_panel(
        draw,
        x0=panel_x0,
        x1=panel_x1,
        y0=box_y0,
        y1=box_y1,
        label=cta_label,
        palette=palette,
    )

    if url:
        display = (url.replace("https://", "").replace("http://", ""))[:34]
        if len(ctx.source_url or "") > 34:
            display = display[:31] + "..."
        ut = f"앱에서 링크 · {display}"
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


def pick_middle_layout(slide: dict[str, Any]) -> str:
    items = _slide_items(slide)
    n = len(items)
    if n == 3:
        return LAYOUT_THREE_COL
    if n == 4:
        return LAYOUT_GRID
    return LAYOUT_NUMBERED


def normalize_to_template_slide(slide: dict[str, Any], *, index: int, total: int) -> dict[str, Any]:
    row = dict(slide)
    if index == 1:
        row["layout_type"] = LAYOUT_COVER
    elif index == total:
        row["layout_type"] = LAYOUT_CTA
    else:
        row["layout_type"] = pick_middle_layout(row)
    return row


def render_template_slide(ctx: TemplateContext) -> Image.Image:
    layout = str(ctx.slide.get("layout_type") or LAYOUT_COVER)
    if layout == LAYOUT_COVER:
        return render_template_cover(ctx)
    if layout == LAYOUT_THREE_COL:
        return render_template_three_col(ctx)
    if layout == LAYOUT_GRID:
        return render_template_grid(ctx)
    if layout == LAYOUT_CTA:
        return render_template_cta(ctx)
    return render_template_numbered(ctx)


def build_template_context(
    slide: dict[str, Any],
    *,
    slide_no: int,
    slide_total: int,
    minister: str,
    mascot: Image.Image | None,
    source_url: str,
    palette: TemplatePalette | None = None,
    hero_image: Image.Image | None = None,
    use_cover_image: bool = False,
) -> TemplateContext:
    pal = palette or resolve_template_palette(str(slide.get("template_palette") or "royal_blue"))
    return TemplateContext(
        slide=slide,
        mascot=mascot,
        slide_no=slide_no,
        slide_total=slide_total,
        minister=minister,
        source_url=source_url,
        palette=pal,
        hero_image=hero_image,
        use_cover_image=use_cover_image,
    )
