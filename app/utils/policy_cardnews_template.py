# 정책 카드뉴스 고정 템플릿

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.utils.policy_cardnews_constants import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CARD_INSET,
    CONTENT_PAD,
    GAP_BLOCK,
    GAP_LINE_LG,
    GAP_LINE_MD,
    GAP_LINE_SM,
    GAP_SECTION,
    OFFSET_PX,
)
from app.utils.policy_cardnews_template_metrics import (
    COVER_MASCOT_MIN_H,
    COVER_MASCOT_ZONE_RATIO,
    CTA_MIN_MASCOT_ZONE,
    GAP_MASCOT,
    MIN_MASCOT_ZONE_H,
)
from app.utils.policy_cardnews_template_draw import (
    fill_scale,
    line_height,
    scaled_size,
    wrap_text,
)
from app.utils.policy_cardnews_mascot import (
    BRAND_ACCENT,
    BRAND_BLUE,
    INK_BLACK,
    draw_classic_speech_bubble,
    draw_mascot_narrator,
)
LAYOUT_COVER = "template_cover"
LAYOUT_NUMBERED = "template_numbered"
LAYOUT_THREE_COL = "template_three_col"
LAYOUT_GRID = "template_grid"
LAYOUT_CTA = "template_cta"

# 2×2 그리드는 캐릭터 미사용 (정보 밀도·중앙 정렬 우선)
MASCOT_LAYOUTS = {LAYOUT_COVER, LAYOUT_CTA, LAYOUT_THREE_COL, LAYOUT_NUMBERED}

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
    font_size = scaled_size(36, fill_scale(50, zone_h, max_scale=1.55), min_size=30, max_size=44)
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
    lines = wrap_text(probe, speech, font, bubble_max_w - 72)[:2] if speech else []
    bh = pad_y * 2 + line_h * len(lines) if lines else 0
    block_h = icon.height + (bh + speech_gap if lines else 0) + GAP_BLOCK * 2
    if block_h > zone_h:
        shrink = max(0.5, zone_h / block_h)
        icon_max = max(90, int(icon_max * shrink))
        icon.thumbnail((int(icon_max * 1.1), icon_max), Image.Resampling.LANCZOS)
        font_size = max(22, int(font_size * shrink))
        font = _load_font(font_size, bold=True)
        line_h = int(font.size * 1.28)
        lines = wrap_text(probe, speech, font, bubble_max_w - 72)[:2] if speech else []
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
    font_size = scaled_size(36, fill_scale(50, zone_h, max_scale=1.55), min_size=30, max_size=44)
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
    from app.utils.policy_cardnews_template_json import (
        render_template_cover,
        render_template_cta,
        render_template_grid,
        render_template_numbered,
        render_template_three_col,
    )

    layout = str(ctx.slide.get("layout_type") or LAYOUT_COVER)
    renderers = {
        LAYOUT_COVER: render_template_cover,
        LAYOUT_CTA: render_template_cta,
        LAYOUT_THREE_COL: render_template_three_col,
        LAYOUT_GRID: render_template_grid,
        LAYOUT_NUMBERED: render_template_numbered,
    }
    return renderers.get(layout, render_template_numbered)(ctx)


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
