from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError

from app.core.config import settings
from app.utils.policy_cardnews_copy import (
    compact_cardnews_slides,
    normalize_slide_copy,
    polish_korean_text,
    should_render_slide,
)
from app.utils.policy_cardnews_mascot import (
    BRAND_ACCENT,
    BRAND_BLUE,
    BRAND_HIGHLIGHT,
    INK_BLACK,
    draw_mascot_narrator,
    pick_mascot,
    pick_pin_mascot,
)
from app.utils.policy_cardnews_typography import (
    draw_label_pill,
    draw_sticker_lines,
    draw_text_stroked,
)
from app.utils.policy_cardnews_visual import (
    SlideVariation,
    apply_blurred_cover_background,
    apply_soft_photo_wash,
    paste_hero_band,
    paste_rounded_image,
    pick_slide_variation,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FONT_DIR = _REPO_ROOT / "app" / "assets" / "fonts"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350
MARGIN = 56
PANEL_RADIUS = 36
BLOCK_RADIUS = 24
PANEL_PAD_X = 36
PANEL_PAD_Y = 32
SECTION_GAP = 20
ITEM_GAP = 16
ITEM_ROW_PAD_X = 20
ITEM_ROW_PAD_Y = 14
NARRATOR_ZONE = 340
MASCOT_MAX_HEIGHT = 320
CONTENT_GAP = 24
COVER_SIDE_PAD = 48

LAYOUT_COVER = "cover_big_typo"
LAYOUT_INFO = "info_blocks"
LAYOUT_CHECKLIST = "checklist"
LAYOUT_QUOTE = "quote_focus"
LAYOUT_CTA = "cta"
LAYOUT_IMAGE = "image_split"
TEMPLATE_LAYOUTS = {
    "template_cover",
    "template_numbered",
    "template_three_col",
    "template_grid",
    "template_cta",
}
VALID_LAYOUTS = {
    LAYOUT_COVER,
    LAYOUT_INFO,
    LAYOUT_CHECKLIST,
    LAYOUT_QUOTE,
    LAYOUT_CTA,
    LAYOUT_IMAGE,
    *TEMPLATE_LAYOUTS,
}
MASCOT_LAYOUTS = {LAYOUT_COVER, LAYOUT_CTA}

THEME_POOL = [
    "cream_warm",
    "mint_fresh",
    "slate_modern",
    "peach_soft",
    "lavender_light",
    "snow_clean",
]

THEME_ALIASES = {
    "policy_blue": "snow_clean",
    "dark_blue": "slate_modern",
    "light_clean": "snow_clean",
    "dark_simple": "slate_modern",
    "app_blue": "snow_clean",
    "app_deep": "slate_modern",
    "app_light": "cream_warm",
    "app_soft": "peach_soft",
    "teal_fresh": "mint_fresh",
    "sunset_coral": "peach_soft",
    "purple_modern": "lavender_light",
    "forest_calm": "mint_fresh",
}

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


@dataclass(frozen=True)
class CardTheme:
    name: str
    gradient_top: tuple[int, int, int]
    gradient_bottom: tuple[int, int, int]
    accent: tuple[int, int, int]
    text_primary: tuple[int, int, int]
    text_body: tuple[int, int, int]
    text_muted: tuple[int, int, int]
    panel_fill: tuple[int, int, int]
    row_fill: tuple[int, int, int]
    row_text: tuple[int, int, int]
    block_fill: tuple[int, int, int]
    overlay_rgba: tuple[int, int, int, int]
    dark: bool


# 브랜드 #1D87FF 기준 통일 팔레트
_BLUE_SOFT = (236, 245, 255)
_BLUE_MID = (214, 233, 255)
_INK = (24, 32, 48)
_INK_BODY = (52, 64, 84)
_INK_MUTED = (108, 120, 142)

THEMES: dict[str, CardTheme] = {
    "cream_warm": CardTheme(
        name="cream_warm",
        gradient_top=(255, 253, 250),
        gradient_bottom=(245, 240, 232),
        accent=BRAND_BLUE,
        text_primary=_INK,
        text_body=_INK_BODY,
        text_muted=_INK_MUTED,
        panel_fill=(255, 255, 255),
        row_fill=_BLUE_SOFT,
        row_text=_INK,
        block_fill=(252, 250, 255),
        overlay_rgba=(0, 0, 0, 0),
        dark=False,
    ),
    "mint_fresh": CardTheme(
        name="mint_fresh",
        gradient_top=(248, 252, 255),
        gradient_bottom=(230, 242, 252),
        accent=BRAND_BLUE,
        text_primary=_INK,
        text_body=_INK_BODY,
        text_muted=_INK_MUTED,
        panel_fill=(255, 255, 255),
        row_fill=_BLUE_SOFT,
        row_text=_INK,
        block_fill=(248, 251, 255),
        overlay_rgba=(0, 0, 0, 0),
        dark=False,
    ),
    "slate_modern": CardTheme(
        name="slate_modern",
        gradient_top=(44, 52, 68),
        gradient_bottom=(28, 34, 46),
        accent=BRAND_BLUE,
        text_primary=(255, 255, 255),
        text_body=(210, 220, 235),
        text_muted=(160, 172, 192),
        panel_fill=(56, 64, 80),
        row_fill=(68, 78, 96),
        row_text=(255, 255, 255),
        block_fill=(62, 72, 90),
        overlay_rgba=(0, 0, 0, 0),
        dark=True,
    ),
    "peach_soft": CardTheme(
        name="peach_soft",
        gradient_top=(255, 251, 252),
        gradient_bottom=(248, 238, 242),
        accent=BRAND_BLUE,
        text_primary=_INK,
        text_body=_INK_BODY,
        text_muted=_INK_MUTED,
        panel_fill=(255, 255, 255),
        row_fill=_BLUE_SOFT,
        row_text=_INK,
        block_fill=(255, 250, 252),
        overlay_rgba=(0, 0, 0, 0),
        dark=False,
    ),
    "lavender_light": CardTheme(
        name="lavender_light",
        gradient_top=(252, 250, 255),
        gradient_bottom=(238, 234, 248),
        accent=BRAND_BLUE,
        text_primary=_INK,
        text_body=_INK_BODY,
        text_muted=_INK_MUTED,
        panel_fill=(255, 255, 255),
        row_fill=_BLUE_SOFT,
        row_text=_INK,
        block_fill=(250, 248, 255),
        overlay_rgba=(0, 0, 0, 0),
        dark=False,
    ),
    "snow_clean": CardTheme(
        name="snow_clean",
        gradient_top=(250, 252, 255),
        gradient_bottom=(235, 241, 250),
        accent=BRAND_BLUE,
        text_primary=_INK,
        text_body=_INK_BODY,
        text_muted=_INK_MUTED,
        panel_fill=(255, 255, 255),
        row_fill=_BLUE_SOFT,
        row_text=_INK,
        block_fill=(245, 249, 255),
        overlay_rgba=(0, 0, 0, 0),
        dark=False,
    ),
}


def _resolve_theme_name(name: str) -> str:
    key = (name or "snow_clean").strip()
    key = THEME_ALIASES.get(key, key)
    return key if key in THEMES else "snow_clean"


@dataclass
class SlideRenderContext:
    slide: dict[str, Any]
    theme: CardTheme
    minister: str
    hero_image: Image.Image | None
    mascot: Image.Image | None
    mascot_name: str
    variation: SlideVariation
    slide_total: int
    rng: random.Random
    source_url: str = ""


def _to_handoff_path(path: Path) -> str:
    try:
        return path.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


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
    if layout in VALID_LAYOUTS:
        return layout
    if index == 1:
        return LAYOUT_COVER
    if index == total:
        return LAYOUT_CTA
    if _parse_items(item.get("items")):
        return LAYOUT_INFO
    return LAYOUT_COVER


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
        theme_name = _resolve_theme_name(str(item.get("theme") or "snow_clean"))
        slides.append(
            {
                "slide": int(item.get("slide") or index),
                "layout_type": _normalize_layout_type(item, index=index, total=total),
                "theme": theme_name,
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
    return slides[:3]


def _content_bottom(*, with_mascot: bool = True) -> int:
    reserve = NARRATOR_ZONE + CONTENT_GAP if with_mascot else CONTENT_GAP
    return CANVAS_HEIGHT - MARGIN - reserve


def _mascot_strip() -> tuple[int, int]:
    top = CANVAS_HEIGHT - MARGIN - NARRATOR_ZONE
    bottom = CANVAS_HEIGHT - MARGIN
    return top, bottom


def apply_deck_slide_themes(
    slides: list[dict[str, Any]],
    *,
    rng: random.Random,
    contentid: str = "",
) -> list[dict[str, Any]]:
    # 한 주제(카드뉴스) 안 모든 슬라이드에 동일 theme
    deck_rng = random.Random(contentid) if contentid else rng
    deck_theme = ""
    for slide in slides:
        candidate = _resolve_theme_name(str(slide.get("theme") or ""))
        if candidate in THEMES:
            deck_theme = candidate
            break
    if not deck_theme:
        deck_theme = deck_rng.choice(THEME_POOL)
    return [{**dict(slide), "theme": deck_theme} for slide in slides]


def diversify_slide_themes(slides: list[dict[str, Any]], *, rng: random.Random) -> list[dict[str, Any]]:
    # 하위 호환: 덱 단위 통일
    return apply_deck_slide_themes(slides, rng=rng)


def _font_dir() -> Path:
    configured = (settings.policy_cardnews_font_dir or "").strip()
    if configured:
        return Path(configured)
    return _DEFAULT_FONT_DIR


def _font_candidates(*, bold: bool, extra_bold: bool = False) -> list[Path]:
    font_dir = _font_dir()
    if extra_bold:
        names = [
            "Pretendard-ExtraBold.ttf",
            "Pretendard-ExtraBold.otf",
            "Pretendard-Bold.ttf",
            "Pretendard-Bold.otf",
        ]
    elif bold:
        names = [
            "Pretendard-Bold.ttf",
            "Pretendard-Bold.otf",
            "Pretendard-SemiBold.ttf",
            "Pretendard-SemiBold.otf",
            "malgunbd.ttf",
        ]
    else:
        names = [
            "Pretendard-Medium.ttf",
            "Pretendard-Medium.otf",
            "Pretendard-Regular.ttf",
            "Pretendard-Regular.otf",
            "malgun.ttf",
        ]

    paths = [font_dir / name for name in names]
    paths.extend(
        [
            Path("C:/Windows/Fonts/malgunbd.ttf") if bold or extra_bold else Path("C:/Windows/Fonts/malgun.ttf"),
            Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
            if bold or extra_bold
            else Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        ]
    )
    return paths


def _load_font(size: int, *, bold: bool = False, extra_bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in _font_candidates(bold=bold, extra_bold=extra_bold):
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    raise RuntimeError(
        "한글 카드뉴스 폰트를 찾을 수 없습니다. "
        "app/assets/fonts/ 에 Pretendard-Bold.otf 등을 넣거나 POLICY_CARDNEWS_FONT_DIR을 설정하세요.",
    )


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    value = (text or "").replace("\n", " ").strip()
    if not value:
        return []

    if " " in value:
        words = value.split()
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    lines = []
    current = ""
    for char in value:
        trial = current + char
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def _fit_font_and_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    *,
    start_size: int,
    max_lines: int,
    bold: bool = False,
    extra_bold: bool = False,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    value = (text or "").strip()
    if not value:
        font = _load_font(start_size, bold=bold, extra_bold=extra_bold)
        return font, []

    for size in range(start_size, 36, -4):
        font = _load_font(size, bold=bold, extra_bold=extra_bold)
        lines = _wrap_text(draw, value, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    font = _load_font(36, bold=bold, extra_bold=extra_bold)
    lines = _wrap_text(draw, value, font, max_width)[:max_lines]
    return font, lines


def _symmetric_content_box() -> tuple[int, int, int]:
    """(left, width, center_x) — 좌우 대칭 콘텐츠 영역."""
    left = COVER_SIDE_PAD
    width = CANVAS_WIDTH - left * 2
    return left, width, CANVAS_WIDTH // 2


def _line_height(font: ImageFont.FreeTypeFont, gap: int = 0) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent + gap


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    gap: int,
) -> int:
    cursor = y
    lh = _line_height(font, gap)
    for line in lines:
        draw.text((x, cursor), line, font=font, fill=fill)
        cursor += lh
    return cursor


def _measure_lines(lines: list[str], font: ImageFont.FreeTypeFont, gap: int) -> int:
    if not lines:
        return 0
    return len(lines) * _line_height(font, gap)


def _measure_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    *,
    gap: int = 0,
) -> tuple[list[str], int]:
    lines = _wrap_text(draw, text, font, max_width) if text else []
    return lines, _measure_lines(lines, font, gap)


def _measure_item_row(
    draw: ImageDraw.ImageDraw,
    item: dict[str, str],
    *,
    label_font: ImageFont.FreeTypeFont,
    value_font: ImageFont.FreeTypeFont,
    text_width: int,
) -> tuple[int, list[str], str]:
    label = str(item.get("label") or "").strip()
    text = str(item.get("text") or "").strip()
    lines = _wrap_text(draw, text, value_font, text_width) if text else []
    height = ITEM_ROW_PAD_Y * 2
    if label:
        height += _line_height(label_font, 4)
    height += _measure_lines(lines, value_font, 4)
    return max(height, 52), lines, label


def _gradient_background(width: int, height: int, theme: CardTheme) -> Image.Image:
    base = Image.new("RGB", (width, height), theme.gradient_top)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(
            int(theme.gradient_top[i] * (1 - ratio) + theme.gradient_bottom[i] * ratio) for i in range(3)
        )
        draw.line([(0, y), (width, y)], fill=color)
    return base


def _normalize_slide_copy(slide: dict[str, Any]) -> dict[str, Any]:
    return normalize_slide_copy(slide)


def _compose_background(theme: CardTheme, overlay: Image.Image | None) -> Image.Image:
    canvas = _gradient_background(CANVAS_WIDTH, CANVAS_HEIGHT, theme).convert("RGBA")
    if overlay is not None:
        cover = overlay.copy()
        cover = cover.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)
        cover = cover.filter(ImageFilter.GaussianBlur(radius=14))
        canvas = Image.alpha_composite(canvas, cover)

    dim = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), theme.overlay_rgba)
    canvas = Image.alpha_composite(canvas, dim)
    return canvas


def _build_slide_background(
    *,
    theme: CardTheme,
    layout: str,
    hero_image: Image.Image | None,
    use_image: bool,
) -> Image.Image:
    canvas = _compose_background(theme, None)
    if not use_image or hero_image is None:
        return canvas
    if layout == LAYOUT_COVER:
        return apply_blurred_cover_background(canvas, hero_image, blur_radius=24, dim_alpha=135)
    if layout == LAYOUT_IMAGE:
        return canvas
    return apply_soft_photo_wash(canvas, hero_image, opacity=0.14)


def _inner_width() -> int:
    return CANVAS_WIDTH - MARGIN * 2 - PANEL_PAD_X * 2


def _content_x() -> int:
    return MARGIN + PANEL_PAD_X


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    theme: CardTheme,
    radius: int = PANEL_RADIUS,
    shadow: bool = True,
) -> None:
    x0, y0, x1, y1 = box
    if y1 - y0 < 24:
        return
    if shadow:
        draw.rounded_rectangle((x0 + 3, y0 + 5, x1 + 3, y1 + 5), radius=radius, fill=(210, 214, 222))
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=theme.panel_fill)


def _draw_panel_shadow(canvas: Image.Image, box: tuple[int, int, int, int], *, radius: int = PANEL_RADIUS) -> Image.Image:
    """패널 그리기 전 부드러운 그림자."""
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((x0 + 4, y0 + 6, x1 + 4, y1 + 6), radius=radius, fill=(0, 0, 0, 45))
    return Image.alpha_composite(canvas.convert("RGBA"), layer)


async def _download_image(url: str, *, timeout: float = 20.0) -> Image.Image | None:
    if not url.startswith(("http://", "https://")):
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            with Image.open(BytesIO(response.content)) as img:
                return img.convert("RGBA")
    except (httpx.HTTPError, UnidentifiedImageError, OSError):
        logger.warning("카드뉴스 배경 이미지 다운로드 실패: %s", url)
        return None


async def _download_images(urls: list[str], *, timeout: float = 20.0) -> list[Image.Image]:
    images: list[Image.Image] = []
    seen: set[str] = set()
    for url in urls:
        url = (url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        img = await _download_image(url, timeout=timeout)
        if img is not None:
            images.append(img)
    return images


def _draw_chrome(
    draw: ImageDraw.ImageDraw,
    *,
    minister: str,
    slide_no: int,
    slide_total: int,
    theme: CardTheme,
) -> int:
    # 상단 바. 반환값 = 콘텐츠 시작 y
    bar_y0 = MARGIN
    bar_y1 = MARGIN + 52
    bar_fill = (255, 255, 255) if not theme.dark else (48, 52, 62)
    draw.rounded_rectangle((MARGIN, bar_y0, CANVAS_WIDTH - MARGIN, bar_y1), radius=16, fill=bar_fill)

    badge_font = _load_font(22, bold=True)
    meta_font = _load_font(20, bold=True)
    minister_color = theme.text_primary if not theme.dark else BRAND_ACCENT

    minister_text = (minister or "").strip()[:16]
    if minister_text:
        draw.text((MARGIN + PANEL_PAD_X, bar_y0 + 13), minister_text, font=badge_font, fill=minister_color)

    slide_label = f"{slide_no:02d}/{slide_total:02d}"
    pill_w = int(draw.textlength(slide_label, font=meta_font)) + 24
    pill_x0 = CANVAS_WIDTH - MARGIN - PANEL_PAD_X - pill_w
    draw.rounded_rectangle((pill_x0, bar_y0 + 10, pill_x0 + pill_w, bar_y1 - 10), radius=14, fill=BRAND_BLUE)
    draw.text((pill_x0 + 12, bar_y0 + 14), slide_label, font=meta_font, fill=BRAND_ACCENT)
    return bar_y1 + SECTION_GAP


def _draw_eyebrow(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    x: int,
    y: int,
    theme: CardTheme,
    centered: bool = False,
) -> int:
    text = (text or "").strip()
    if not text:
        return y
    font = _load_font(24, bold=True)
    pill_w = int(draw.textlength(text, font=font)) + 32
    pill_x = (CANVAS_WIDTH - pill_w) // 2 if centered else x
    draw.rounded_rectangle((pill_x, y, pill_x + pill_w, y + 40), radius=14, fill=BRAND_BLUE)
    draw.text((pill_x + 16, y + 7), text, font=font, fill=BRAND_ACCENT)
    return y + 56


def _draw_narrator(canvas: Image.Image, ctx: SlideRenderContext) -> Image.Image:
    layout = str(ctx.slide.get("layout_type") or LAYOUT_COVER)
    if layout not in MASCOT_LAYOUTS:
        return canvas
    speech = str(ctx.slide.get("speech") or "").strip()
    if not speech or ctx.mascot is None:
        return canvas
    strip_top, strip_bottom = _mascot_strip()
    font = _load_font(28, bold=True)
    return draw_mascot_narrator(
        canvas,
        ctx.mascot,
        speech,
        font=font,
        strip_top=strip_top,
        strip_bottom=strip_bottom,
        bubble_fill=(255, 255, 255),
        text_fill=INK_BLACK,
        mascot_max_height=MASCOT_MAX_HEIGHT,
        margin=MARGIN - 12,
        gap=28,
    )


def _draw_check_icon(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    color: tuple[int, int, int],
    size: int = 24,
) -> None:
    draw.line([(x, y + size // 2), (x + size // 3, y + size)], fill=color, width=4)
    draw.line([(x + size // 3, y + size), (x + size, y + size // 4)], fill=color, width=4)


def _render_cover_big_typo(canvas: Image.Image, *, ctx: SlideRenderContext) -> Image.Image:
    slide, theme, minister = ctx.slide, ctx.theme, ctx.minister
    draw = ImageDraw.Draw(canvas)
    slide_no = int(slide.get("slide") or 1)
    content_top = _draw_chrome(
        draw, minister=minister, slide_no=slide_no, slide_total=ctx.slide_total, theme=theme
    )

    highlight = str(slide.get("highlight") or "").strip()
    headline = str(slide.get("headline") or "").strip()
    body = str(slide.get("body") or slide.get("subtext") or "").strip()
    eyebrow = str(slide.get("eyebrow") or "").strip()

    content_left, content_w, _cx = _symmetric_content_box()
    zone_top = content_top + 28
    zone_bottom = _content_bottom(with_mascot=True) - 20

    highlight_font, highlight_lines = _fit_font_and_lines(
        draw, highlight, content_w, start_size=96, max_lines=2, extra_bold=True
    )
    headline_font, headline_lines = (
        _fit_font_and_lines(draw, headline, content_w, start_size=72, max_lines=2, extra_bold=True)
        if headline and headline != highlight
        else (_load_font(72, extra_bold=True), [])
    )
    body_font, body_lines = _fit_font_and_lines(
        draw, body, content_w, start_size=34, max_lines=2, bold=True
    )

    if not (highlight_lines or headline_lines or body_lines):
        return _draw_narrator(canvas, ctx)

    block_h = 0
    if eyebrow:
        block_h += 56
    block_h += _measure_lines(highlight_lines, highlight_font, 12)
    block_h += _measure_lines(headline_lines, headline_font, 10) + (12 if headline_lines else 0)
    block_h += _measure_lines(body_lines, body_font, 8) + (12 if body_lines else 0)
    block_h += 24

    cursor = zone_top + max(0, (zone_bottom - zone_top - block_h) // 2)
    cursor = _draw_eyebrow(draw, text=eyebrow, x=content_left, y=cursor, theme=theme, centered=True)

    if highlight_lines:
        cursor = draw_sticker_lines(
            draw,
            lines=highlight_lines,
            font=highlight_font,
            x=content_left,
            y=cursor,
            fill=BRAND_BLUE,
            stroke_fill=INK_BLACK,
            stroke_width=7,
            gap=12,
            center_width=content_w,
            line_height_fn=_line_height,
        ) + 12
    if headline_lines:
        cursor = draw_sticker_lines(
            draw,
            lines=headline_lines,
            font=headline_font,
            x=content_left,
            y=cursor,
            fill=(255, 255, 255),
            stroke_fill=INK_BLACK,
            stroke_width=6,
            gap=10,
            center_width=content_w,
            line_height_fn=_line_height,
        ) + 12
    if body_lines:
        for line in body_lines:
            lw = int(draw.textlength(line, font=body_font))
            draw_text_stroked(
                draw,
                (content_left + (content_w - lw) // 2, cursor),
                line,
                body_font,
                fill=(28, 34, 48),
                stroke_fill=(255, 255, 255),
                stroke_width=3,
            )
            cursor += _line_height(body_font, 8)
    return _draw_narrator(canvas, ctx)


def _draw_brand_check(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    size: int = 32,
) -> None:
    draw.ellipse((x, y, x + size, y + size), fill=BRAND_BLUE)
    cx, cy = x + size // 2, y + size // 2
    draw.line([(cx - 8, cy), (cx - 2, cy + 7), (cx + 10, cy - 8)], fill=BRAND_ACCENT, width=4)


def _render_info_blocks(canvas: Image.Image, *, ctx: SlideRenderContext) -> Image.Image:
    slide, theme, minister = ctx.slide, ctx.theme, ctx.minister
    slide_no = int(slide.get("slide") or 1)
    draw = ImageDraw.Draw(canvas)
    content_top = _draw_chrome(
        draw, minister=minister, slide_no=slide_no, slide_total=ctx.slide_total, theme=theme
    )

    photo_h = 300
    has_photo = ctx.hero_image is not None and slide.get("use_image", True)
    if has_photo:
        photo_bottom = content_top + photo_h
        canvas = paste_rounded_image(
            canvas,
            ctx.hero_image,
            box=(MARGIN, content_top, CANVAS_WIDTH - MARGIN, photo_bottom),
            radius=32,
        )
        draw = ImageDraw.Draw(canvas)
        panel_y0 = photo_bottom + SECTION_GAP
    else:
        panel_y0 = content_top + SECTION_GAP

    panel_x0, panel_x1 = MARGIN, CANVAS_WIDTH - MARGIN
    info_pad_x, info_pad_y = 44, 40
    tx = panel_x0 + info_pad_x
    inner_w = panel_x1 - panel_x0 - info_pad_x * 2
    col_gap = 20
    col_w = (inner_w - col_gap) // 2
    tile_pad_x, tile_pad_y = 26, 24

    headline_font = _load_font(46, bold=True)
    label_font = _load_font(24, bold=True)
    value_font = _load_font(38, bold=True)

    eyebrow = str(slide.get("eyebrow") or "").strip()
    headline = str(slide.get("headline") or "").strip()
    items = [i for i in list(slide.get("items") or []) if str(i.get("text") or "").strip()][:6]
    if not items and slide.get("body"):
        items = [{"label": "요약", "text": line.strip()} for line in str(slide["body"]).split("\n") if line.strip()][:6]

    headline_lines, headline_h = _measure_wrapped(draw, headline, headline_font, inner_w, gap=8)

    tiles: list[tuple[int, int, list[str], str]] = []
    for index, item in enumerate(items):
        label = str(item.get("label") or f"포인트{index + 1}").strip()
        text = str(item.get("text") or "").strip()
        lines = _wrap_text(draw, text, value_font, col_w - tile_pad_x * 2)
        tiles.append((index % 2, index // 2, lines, label))

    row_count = max((row for _, row, _, _ in tiles), default=-1) + 1
    row_heights: list[int] = []
    for row_index in range(row_count):
        max_h = 108
        for col_index in range(2):
            for col, row, lines, _label in tiles:
                if col == col_index and row == row_index:
                    h = tile_pad_y * 2 + 44 + _measure_lines(lines, value_font, 6)
                    max_h = max(max_h, h)
        row_heights.append(max_h)

    tiles_h = sum(row_heights) + 22 * max(row_count - 1, 0)
    content_bottom = _content_bottom(with_mascot=False)
    panel_y1 = content_bottom

    canvas = _draw_panel_shadow(canvas, (panel_x0, panel_y0, panel_x1, panel_y1))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (panel_x0, panel_y0, panel_x1, panel_y1),
        radius=PANEL_RADIUS,
        fill=_BLUE_SOFT,
    )

    header_h = info_pad_y + (56 if eyebrow else 0) + headline_h + SECTION_GAP
    grid_h = tiles_h
    free_h = max(panel_y1 - panel_y0 - header_h - grid_h - info_pad_y, 0)
    cursor = panel_y0 + info_pad_y + free_h // 4

    cursor = _draw_eyebrow(draw, text=eyebrow, x=tx, y=cursor, theme=theme, centered=True)
    if headline_lines:
        for line in headline_lines:
            lw = int(draw.textlength(line, font=headline_font))
            draw.text((tx + (inner_w - lw) // 2, cursor), line, font=headline_font, fill=BRAND_BLUE)
            cursor += _line_height(headline_font, 10)
        cursor += SECTION_GAP + 4

    grid_y = cursor + free_h // 4
    for row_index, row_h in enumerate(row_heights):
        for col_index in range(2):
            match = next((t for t in tiles if t[0] == col_index and t[1] == row_index), None)
            if match is None:
                continue
            _col, _row, lines, label = match
            tile_x0 = tx + col_index * (col_w + col_gap)
            tile_x1 = tile_x0 + col_w
            tile_y0 = grid_y
            tile_y1 = tile_y0 + row_h
            draw.rounded_rectangle((tile_x0 + 2, tile_y0 + 4, tile_x1 + 2, tile_y1 + 4), radius=BLOCK_RADIUS, fill=(210, 218, 230))
            draw.rounded_rectangle((tile_x0, tile_y0, tile_x1, tile_y1), radius=BLOCK_RADIUS, fill=(255, 255, 255))
            ix = tile_x0 + tile_pad_x
            iy = tile_y0 + tile_pad_y
            _pw, ph = draw_label_pill(draw, x=ix, y=iy, text=label, font=label_font, fill=BRAND_BLUE, text_fill=BRAND_ACCENT)
            iy += ph + 14
            for line in lines:
                draw.text((ix, iy), line, font=value_font, fill=_INK)
                iy += _line_height(value_font, 6)
        grid_y += row_h + 22

    return canvas


def _render_checklist(canvas: Image.Image, *, ctx: SlideRenderContext) -> Image.Image:
    slide, theme, minister = ctx.slide, ctx.theme, ctx.minister
    draw = ImageDraw.Draw(canvas)
    slide_no = int(slide.get("slide") or 1)
    cursor = _draw_chrome(
        draw, minister=minister, slide_no=slide_no, slide_total=ctx.slide_total, theme=theme
    )

    headline_font = _load_font(48, bold=True)
    item_font = _load_font(34)
    inner_w = _inner_width()
    tx = _content_x()
    check_x = MARGIN + PANEL_PAD_X + 4
    text_x = check_x + 52
    text_w = CANVAS_WIDTH - MARGIN - PANEL_PAD_X - text_x
    eyebrow = str(slide.get("eyebrow") or "").strip()
    headline = str(slide.get("headline") or "").strip()

    items = [i for i in list(slide.get("items") or []) if str(i.get("text") or "").strip()]
    if not items and slide.get("body"):
        items = [{"label": "", "text": line.strip()} for line in str(slide["body"]).split("\n") if line.strip()]

    rows = items[:6]
    row_heights: list[tuple[int, list[str]]] = []
    for item in rows:
        text = str(item.get("text") or "").strip()
        lines, h = _measure_wrapped(draw, text, item_font, text_w, gap=4)
        row_heights.append((max(h, 44), lines))

    headline_lines, headline_h = _measure_wrapped(draw, headline, headline_font, inner_w, gap=6)
    content_h = PANEL_PAD_Y * 2
    if eyebrow:
        content_h += 56
    content_h += headline_h + (SECTION_GAP if headline_lines else 0)
    content_h += sum(h for h, _ in row_heights) + ITEM_GAP * max(len(row_heights) - 1, 0)

    panel_y0 = cursor + SECTION_GAP
    panel_y1 = min(panel_y0 + content_h, _content_bottom(with_mascot=False))
    if panel_y1 <= panel_y0 + PANEL_PAD_Y:
        return canvas
    _draw_panel(draw, box=(MARGIN, panel_y0, CANVAS_WIDTH - MARGIN, panel_y1), theme=theme)
    cursor = panel_y0 + PANEL_PAD_Y
    cursor = _draw_eyebrow(draw, text=eyebrow, x=tx, y=cursor, theme=theme)

    if headline_lines:
        cursor = _draw_lines(draw, x=tx, y=cursor, lines=headline_lines, font=headline_font, fill=theme.text_primary, gap=6)
        cursor += SECTION_GAP

    check_size = 34
    for (row_h, lines), _item in zip(row_heights, rows, strict=False):
        row_y = cursor
        _draw_brand_check(draw, x=check_x, y=row_y + max(4, (row_h - check_size) // 2), size=check_size)
        ty = row_y + 4
        for line in lines:
            draw.text((text_x, ty), line, font=item_font, fill=theme.row_text)
            ty += _line_height(item_font, 4)
        cursor += row_h + ITEM_GAP
    return canvas


def _render_quote_focus(canvas: Image.Image, *, ctx: SlideRenderContext) -> Image.Image:
    slide, theme, minister = ctx.slide, ctx.theme, ctx.minister
    draw = ImageDraw.Draw(canvas)
    slide_no = int(slide.get("slide") or 1)
    top = _draw_chrome(
        draw, minister=minister, slide_no=slide_no, slide_total=ctx.slide_total, theme=theme
    )

    quote_font = _load_font(64, extra_bold=True)
    sub_font = _load_font(38, bold=True)
    body_font = _load_font(32)

    quote = str(slide.get("highlight") or "").strip()
    sub = str(slide.get("headline") or "").strip()
    if quote and sub == quote:
        sub = str(slide.get("subtext") or "").strip()
    body = str(slide.get("body") or "").strip()

    centered = ctx.variation.quote_align == "center"
    inner_w = _inner_width() - (16 if centered else 0)
    tx = _content_x()
    lines_h = PANEL_PAD_Y * 2
    eyebrow = str(slide.get("eyebrow") or "").strip()
    if eyebrow:
        lines_h += 56
    quote_lines = _wrap_text(draw, quote, quote_font, inner_w) if quote else []
    sub_lines = _wrap_text(draw, sub, sub_font, inner_w) if sub else []
    body_lines = _wrap_text(draw, body, body_font, inner_w) if body else []
    lines_h += _measure_lines(quote_lines, quote_font, 8)
    lines_h += _measure_lines(sub_lines, sub_font, 6) + (SECTION_GAP if sub_lines else 0)
    lines_h += _measure_lines(body_lines, body_font, 6) + (SECTION_GAP if body_lines else 0)

    if not (quote_lines or sub_lines or body_lines):
        return canvas

    panel_x0, panel_x1 = MARGIN, CANVAS_WIDTH - MARGIN
    panel_y0 = top + SECTION_GAP
    panel_y1 = min(panel_y0 + lines_h, _content_bottom(with_mascot=False))
    _draw_panel(draw, box=(panel_x0, panel_y0, panel_x1, panel_y1), theme=theme)

    cursor = panel_y0 + PANEL_PAD_Y
    if eyebrow:
        if centered:
            ew = int(draw.textlength(eyebrow, font=_load_font(24, bold=True)))
            _draw_eyebrow(draw, text=eyebrow, x=(CANVAS_WIDTH - ew - 32) // 2, y=cursor, theme=theme)
        else:
            cursor = _draw_eyebrow(draw, text=eyebrow, x=tx, y=cursor, theme=theme)
    if quote_lines:
        if centered:
            for line in quote_lines:
                w = int(draw.textlength(line, font=quote_font))
                draw.text(((CANVAS_WIDTH - w) // 2, cursor), line, font=quote_font, fill=theme.accent)
                cursor += _line_height(quote_font, 8)
        else:
            cursor = _draw_lines(draw, x=tx, y=cursor, lines=quote_lines, font=quote_font, fill=theme.accent, gap=8)
        cursor += SECTION_GAP
    if sub_lines:
        if centered:
            for line in sub_lines:
                w = int(draw.textlength(line, font=sub_font))
                draw.text(((CANVAS_WIDTH - w) // 2, cursor), line, font=sub_font, fill=theme.text_primary)
                cursor += _line_height(sub_font, 6)
        else:
            cursor = _draw_lines(draw, x=tx, y=cursor, lines=sub_lines, font=sub_font, fill=theme.text_primary, gap=6) + SECTION_GAP
    if body_lines:
        if centered:
            for line in body_lines:
                w = int(draw.textlength(line, font=body_font))
                draw.text(((CANVAS_WIDTH - w) // 2, cursor), line, font=body_font, fill=theme.text_body)
                cursor += _line_height(body_font, 6)
        else:
            _draw_lines(draw, x=tx, y=cursor, lines=body_lines, font=body_font, fill=theme.text_body, gap=6)
    return canvas


def _render_image_split(canvas: Image.Image, *, ctx: SlideRenderContext) -> Image.Image:
    slide, theme, minister = ctx.slide, ctx.theme, ctx.minister
    draw = ImageDraw.Draw(canvas)
    slide_no = int(slide.get("slide") or 1)
    top = _draw_chrome(
        draw, minister=minister, slide_no=slide_no, slide_total=ctx.slide_total, theme=theme
    )

    photo_top = top
    photo_bottom = photo_top + ctx.variation.hero_height
    if ctx.hero_image is not None and ctx.slide.get("use_image", True):
        canvas = paste_rounded_image(
            canvas,
            ctx.hero_image,
            box=(MARGIN, photo_top, CANVAS_WIDTH - MARGIN, photo_bottom),
            radius=ctx.variation.photo_radius,
        )
        draw = ImageDraw.Draw(canvas)

    headline_font = _load_font(48, bold=True)
    body_font = _load_font(32)
    inner_w = _inner_width()
    tx = _content_x()
    eyebrow = str(slide.get("eyebrow") or "").strip()

    headline = str(slide.get("headline") or slide.get("highlight") or "").strip()
    body = str(slide.get("body") or slide.get("subtext") or "").strip()
    headline_lines = _wrap_text(draw, headline, headline_font, inner_w) if headline else []
    body_lines = _wrap_text(draw, body, body_font, inner_w) if body else []

    if not (headline_lines or body_lines):
        return canvas

    text_h = PANEL_PAD_Y * 2
    if eyebrow:
        text_h += 56
    text_h += _measure_lines(headline_lines, headline_font, 6)
    text_h += _measure_lines(body_lines, body_font, 6) + (SECTION_GAP if body_lines else 0)

    panel_y1 = CANVAS_HEIGHT - MARGIN
    panel_y0 = max(photo_bottom + SECTION_GAP, panel_y1 - text_h)
    _draw_panel(draw, box=(MARGIN, panel_y0, CANVAS_WIDTH - MARGIN, panel_y1), theme=theme)
    cursor = panel_y0 + PANEL_PAD_Y
    cursor = _draw_eyebrow(draw, text=eyebrow, x=tx, y=cursor, theme=theme)
    if headline_lines:
        cursor = _draw_lines(draw, x=tx, y=cursor, lines=headline_lines, font=headline_font, fill=theme.text_primary, gap=6) + 10
    if body_lines:
        _draw_lines(draw, x=tx, y=cursor, lines=body_lines, font=body_font, fill=theme.text_body, gap=6)
    return canvas


def _draw_link_style_text(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> int:
    draw.text((x, y), text, font=font, fill=fill)
    w = int(draw.textlength(text, font=font))
    underline_y = y + _line_height(font, 0) - 6
    draw.line([(x, underline_y), (x + w, underline_y)], fill=fill, width=2)
    return y + _line_height(font, 6)


def _render_cta(canvas: Image.Image, *, ctx: SlideRenderContext) -> Image.Image:
    slide, theme, minister = ctx.slide, ctx.theme, ctx.minister
    slide_no = int(slide.get("slide") or 1)
    draw = ImageDraw.Draw(canvas)
    top = _draw_chrome(
        draw, minister=minister, slide_no=slide_no, slide_total=ctx.slide_total, theme=theme
    )

    headline_font = _load_font(46, bold=True)
    body_font = _load_font(30, bold=True)
    cta_font = _load_font(38, bold=True)
    bullet_font = _load_font(28, bold=True)
    url_font = _load_font(24, bold=True)
    cx = CANVAS_WIDTH // 2
    content_left, content_w, _ = _symmetric_content_box()

    headline = str(slide.get("headline") or "").strip()
    cta_text = str(slide.get("cta") or "원문 뉴스 보기").strip()
    body = str(slide.get("body") or "").strip()
    eyebrow = str(slide.get("eyebrow") or "마무리").strip()
    source_url = (ctx.source_url or "").strip()

    bullets: list[str] = []
    for item in slide.get("items") or []:
        text = str(item.get("text") if isinstance(item, dict) else item).strip()
        if text:
            bullets.append(text)
    if not bullets and body:
        bullets = [line.strip() for line in body.split("\n") if line.strip()][:4]
        body = ""

    panel_y0 = top + SECTION_GAP
    panel_y1 = _content_bottom(with_mascot=True)
    canvas = _draw_panel_shadow(canvas, (MARGIN, panel_y0, CANVAS_WIDTH - MARGIN, panel_y1))
    draw = ImageDraw.Draw(canvas)
    _draw_panel(draw, box=(MARGIN, panel_y0, CANVAS_WIDTH - MARGIN, panel_y1), theme=theme)

    headline_lines, _ = _measure_wrapped(draw, headline, headline_font, content_w, gap=8)
    body_lines, _ = _measure_wrapped(draw, body, body_font, content_w, gap=6) if body else ([], 0)
    bullet_lines: list[str] = []
    for bullet in bullets[:4]:
        for line in _wrap_text(draw, f"• {bullet}", bullet_font, content_w):
            bullet_lines.append(line)

    block_h = PANEL_PAD_Y * 2 + 56
    block_h += _measure_lines(headline_lines, headline_font, 8) + 24
    block_h += 92 + 20
    block_h += len(bullet_lines) * _line_height(bullet_font, 6)
    block_h += _measure_lines(body_lines, body_font, 6)
    if source_url:
        block_h += 44

    cursor = panel_y0 + max(PANEL_PAD_Y, (panel_y1 - panel_y0 - block_h) // 3)
    cursor = _draw_eyebrow(draw, text=eyebrow, x=content_left, y=cursor, theme=theme, centered=True)

    for line in headline_lines:
        w = int(draw.textlength(line, font=headline_font))
        draw.text((cx - w // 2, cursor), line, font=headline_font, fill=theme.text_primary)
        cursor += _line_height(headline_font, 8)
    cursor += 20

    btn_w = min(content_w, max(int(draw.textlength(cta_text, font=cta_font)) + 96, 360))
    btn_x0 = cx - btn_w // 2
    btn_y0 = cursor
    btn_y1 = btn_y0 + 88
    draw.rounded_rectangle((btn_x0, btn_y0, btn_x0 + btn_w, btn_y1), radius=44, fill=BRAND_BLUE)
    tw = int(draw.textlength(cta_text, font=cta_font))
    draw.text((cx - tw // 2, btn_y0 + 22), cta_text, font=cta_font, fill=BRAND_ACCENT)
    cursor = btn_y1 + 24

    for line in bullet_lines:
        w = int(draw.textlength(line, font=bullet_font))
        draw.text((cx - w // 2, cursor), line, font=bullet_font, fill=theme.text_body)
        cursor += _line_height(bullet_font, 6)
    cursor += 8

    for line in body_lines:
        w = int(draw.textlength(line, font=body_font))
        draw.text((cx - w // 2, cursor), line, font=body_font, fill=theme.text_muted)
        cursor += _line_height(body_font, 6)

    if source_url:
        display_url = source_url.replace("https://", "").replace("http://", "")
        if len(display_url) > 42:
            display_url = display_url[:39] + "..."
        url_label = f"원문 링크 · {display_url}"
        uw = int(draw.textlength(url_label, font=url_font))
        cursor = _draw_link_style_text(
            draw,
            x=cx - uw // 2,
            y=cursor + 8,
            text=url_label,
            font=url_font,
            fill=BRAND_BLUE,
        )

    return _draw_narrator(canvas, ctx)


_LAYOUT_RENDERERS: dict[str, Callable[..., Image.Image]] = {
    LAYOUT_COVER: _render_cover_big_typo,
    LAYOUT_INFO: _render_info_blocks,
    LAYOUT_CHECKLIST: _render_checklist,
    LAYOUT_QUOTE: _render_quote_focus,
    LAYOUT_CTA: _render_cta,
    LAYOUT_IMAGE: _render_image_split,
}


def _render_slide_image(*, ctx: SlideRenderContext, background: Image.Image) -> Image.Image:
    if settings.policy_cardnews_use_template:
        from app.utils.policy_cardnews_template import (
            build_template_context,
            normalize_to_template_slide,
            render_template_slide,
            resolve_template_palette,
        )

        slide_no = int(ctx.slide.get("slide") or 1)
        slide = normalize_to_template_slide(ctx.slide, index=slide_no, total=ctx.slide_total)
        tmpl_ctx = build_template_context(
            slide,
            slide_no=slide_no,
            slide_total=ctx.slide_total,
            minister=ctx.minister,
            mascot=ctx.mascot,
            source_url=ctx.source_url,
            palette=resolve_template_palette(str(slide.get("template_palette") or "royal_blue")),
            hero_image=ctx.hero_image,
            use_cover_image=bool(ctx.hero_image) and slide_no == 1,
        )
        return render_template_slide(tmpl_ctx)

    canvas = background.copy().convert("RGBA")
    layout = str(ctx.slide.get("layout_type") or LAYOUT_COVER)
    renderer = _LAYOUT_RENDERERS.get(layout, _render_cover_big_typo)
    return renderer(canvas, ctx=ctx).convert("RGB")


def save_slide_image_bytes(
    *,
    contentid: str,
    slide_no: int,
    image_bytes: bytes,
    output_dir: Path,
) -> str:
    target_dir = output_dir / contentid
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"slide_{slide_no:02d}.png"
    out_path.write_bytes(image_bytes)
    return _to_handoff_path(out_path)


async def render_policy_cardnews_slides(
    *,
    contentid: str,
    slides: list[dict[str, Any]],
    output_dir: Path,
    minister: str = "",
    image_urls: list[str] | None = None,
    background_image_url: str | None = None,
    source_url: str = "",
    pin_content: str = "",
) -> list[str]:
    target_dir = output_dir / contentid
    target_dir.mkdir(parents=True, exist_ok=True)

    urls = [u for u in (image_urls or []) if str(u).strip()]
    if background_image_url and background_image_url not in urls:
        urls.insert(0, background_image_url)
    photos = await _download_images(urls[:8])

    rng = random.Random()
    prepared = [_normalize_slide_copy(s) for s in slides]
    if settings.policy_cardnews_use_template:
        from app.utils.policy_cardnews_template import apply_deck_template_theme

        prepared = apply_deck_template_theme(prepared, rng=rng, contentid=contentid)
    else:
        prepared = apply_deck_slide_themes(prepared, rng=rng, contentid=contentid)
    prepared = compact_cardnews_slides(prepared)
    from app.utils.policy_cardnews_terms import enrich_cardnews_terminology

    prepared = enrich_cardnews_terminology(prepared, pin_content=pin_content)
    prepared = [_normalize_slide_copy(s) for s in prepared]
    slides_to_render = [s for s in prepared if should_render_slide(s)]
    if not slides_to_render:
        raise ValueError("렌더링할 카드뉴스 슬라이드가 없습니다 (내용 부족)")

    slide_total = len(slides_to_render)
    saved_paths: list[str] = []
    for index, slide in enumerate(slides_to_render, start=1):
        slide = dict(slide)
        slide["slide"] = index
        slide_no = index
        layout = str(slide.get("layout_type") or LAYOUT_COVER)
        if settings.policy_cardnews_use_template:
            from app.utils.policy_cardnews_template import (
                LAYOUT_COVER as TMPL_COVER,
                MASCOT_LAYOUTS as TMPL_MASCOT_LAYOUTS,
                resolve_template_palette,
            )

            mascot_layouts = TMPL_MASCOT_LAYOUTS
            is_cover = layout == TMPL_COVER or slide_no == 1
        else:
            mascot_layouts = MASCOT_LAYOUTS
            is_cover = layout == LAYOUT_COVER or slide_no == 1

        theme = THEMES.get(_resolve_theme_name(str(slide.get("theme") or "snow_clean")), THEMES["snow_clean"])
        variation = pick_slide_variation(rng, layout=layout)
        use_image = bool(slide.get("use_image", True)) and bool(photos)
        cover_photo = photos[0] if photos else None
        hero = cover_photo if is_cover else (photos[index % len(photos)] if photos else None)
        use_cover_image = is_cover and cover_photo is not None

        mascot_name = ""
        mascot = None
        is_cta = slide_no == slide_total or layout in {"template_cta", "cta"}
        need_mascot = layout in mascot_layouts and not (is_cover and use_cover_image)
        if is_cta:
            mascot_pick = pick_pin_mascot(rng)
            mascot_name = mascot_pick[0] if mascot_pick else ""
            mascot = mascot_pick[1] if mascot_pick else None
        elif need_mascot:
            mascot_pick = pick_mascot(rng)
            mascot_name = mascot_pick[0] if mascot_pick else ""
            mascot = mascot_pick[1] if mascot_pick else None

        palette = (
            resolve_template_palette(str(slide.get("template_palette") or "royal_blue"))
            if settings.policy_cardnews_use_template
            else None
        )

        ctx = SlideRenderContext(
            slide=slide,
            theme=theme,
            minister=minister,
            hero_image=hero,
            mascot=mascot,
            mascot_name=mascot_name,
            variation=variation,
            slide_total=slide_total,
            rng=rng,
            source_url=source_url,
        )
        if settings.policy_cardnews_use_template:
            background = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), palette.outer)  # type: ignore[union-attr]
        else:
            background = _build_slide_background(
                theme=theme,
                layout=layout,
                hero_image=hero,
                use_image=use_image,
            )
        out_path = target_dir / f"slide_{slide_no:02d}.png"
        image = _render_slide_image(ctx=ctx, background=background)
        image.save(out_path, format="PNG")
        saved_paths.append(_to_handoff_path(out_path))

    return saved_paths
