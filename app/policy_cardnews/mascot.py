from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.policy_cardnews.paths import cardnews_mascot_dir

logger = logging.getLogger(__name__)

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350
MANIFEST_NAME = "mascots.json"

BRAND_BLUE = (29, 135, 255)
BRAND_ACCENT = (255, 255, 255)
BRAND_HIGHLIGHT = (255, 230, 90)
INK_BLACK = (18, 20, 26)

_MASCOT_CACHE: tuple[tuple[str, Image.Image], ...] | None = None
_MASCOT_CACHE_KEY: tuple[str, float] | None = None
_ALLOWED_NAMES: frozenset[str] | None = None


def mascot_dir() -> Path:
    return cardnews_mascot_dir()


def _manifest_mtime(directory: Path) -> float:
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        return 0.0
    return manifest.stat().st_mtime


def _read_manifest_filenames(directory: Path) -> list[str]:
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        logger.warning(
            "mascots.json 없음 — 캐릭터 미사용. %s/%s 에 files 목록을 작성하세요.",
            directory,
            MANIFEST_NAME,
        )
        return []

    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("mascots.json 읽기 실패: %s", exc)
        return []

    if isinstance(payload, list):
        return [str(name).strip() for name in payload if str(name).strip()]
    if isinstance(payload, dict):
        raw = payload.get("files") or []
        if isinstance(raw, list):
            return [str(name).strip() for name in raw if str(name).strip()]
    logger.warning("mascots.json 형식 오류 — files 배열이 필요합니다.")
    return []


def allowed_mascot_names() -> frozenset[str]:
    global _ALLOWED_NAMES
    directory = mascot_dir()
    names = _read_manifest_filenames(directory)
    _ALLOWED_NAMES = frozenset(names)
    return _ALLOWED_NAMES


def load_mascots() -> tuple[tuple[str, Image.Image], ...]:
    # mascots.json files 목록에 있는 PNG만 로드
    global _MASCOT_CACHE, _MASCOT_CACHE_KEY

    directory = mascot_dir()
    cache_key = (str(directory.resolve()), _manifest_mtime(directory))
    if _MASCOT_CACHE is not None and _MASCOT_CACHE_KEY == cache_key:
        return _MASCOT_CACHE

    allowed = allowed_mascot_names()
    if not allowed:
        _MASCOT_CACHE = ()
        _MASCOT_CACHE_KEY = cache_key
        return _MASCOT_CACHE

    loaded: list[tuple[str, Image.Image]] = []
    for name in sorted(allowed):
        path = (directory / name).resolve()
        if path.parent.resolve() != directory.resolve():
            logger.warning("mascots.json 경로 이탈 차단: %s", name)
            continue
        if not path.is_file():
            logger.warning("mascots.json 항목 없음: %s", path)
            continue
        try:
            with Image.open(path) as img:
                rgba = img.convert("RGBA")
                cleaned = _trim_alpha(rgba)
                if cleaned.size[0] < 24 or cleaned.size[1] < 24:
                    logger.warning("캐릭터 PNG 너무 작음: %s", name)
                    continue
                loaded.append((name, cleaned))
        except OSError:
            logger.warning("캐릭터 PNG 로드 실패: %s", name)

    if not loaded:
        logger.warning("mascots.json에 등록된 사용 가능한 캐릭터가 없습니다: %s", directory)
    else:
        logger.info("캐릭터 %d개 로드 (manifest 전용): %s", len(loaded), ", ".join(n for n, _ in loaded))

    _MASCOT_CACHE = tuple(loaded)
    _MASCOT_CACHE_KEY = cache_key
    return _MASCOT_CACHE


def pick_mascot(rng: random.Random) -> tuple[str, Image.Image] | None:
    # manifest 등록 파일만 무작위 선택
    mascots = load_mascots()
    if not mascots:
        return None
    name, image = mascots[rng.randrange(len(mascots))]
    logger.info("카드뉴스 캐릭터 선택: %s", name)
    return name, image.copy()


def pick_pin_mascot(
    rng: random.Random,
) -> tuple[str, Image.Image] | None:
    # 마무리 등 — app/assets/mascots (mascots.json) 핀 캐릭터만 사용
    mascots = load_mascots()
    if not mascots:
        logger.warning("mascots.json 핀 캐릭터 없음 — 마무리 캐릭터 생략")
        return None
    name, image = mascots[rng.randrange(len(mascots))]
    logger.info("카드뉴스 핀 캐릭터(마무리): %s", name)
    return name, image.copy()


def _trim_alpha(img: Image.Image) -> Image.Image:
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return img
    return img.crop(bbox)


def _wrap_speech_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if char == " " and current:
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                lines.append(current.strip())
                current = ""
            continue
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current.strip())
            current = char
    if current.strip():
        lines.append(current.strip())
    return lines[:3]


BUBBLE_FILL = (255, 255, 255)
BUBBLE_OUTLINE = (32, 36, 48)


def draw_classic_speech_bubble(
    draw: ImageDraw.ImageDraw,
    *,
    bx0: int,
    by0: int,
    bx1: int,
    by1: int,
    tail_tip: tuple[int, int],
    tail_from_side: str = "left",
    fill: tuple[int, int, int] = BUBBLE_FILL,
    outline: tuple[int, int, int] = BUBBLE_OUTLINE,
    outline_width: int = 3,
    radius: int = 28,
) -> None:
    """흰색 라운드 말풍선 + 꼬리(캐릭터 방향)."""
    draw.rounded_rectangle(
        (bx0, by0, bx1, by1),
        radius=radius,
        fill=fill,
        outline=outline,
        width=outline_width,
    )
    tip_x, tip_y = tail_tip
    if tail_from_side == "left":
        mid_y = (by0 + by1) // 2
        base_x = bx0 + max(6, radius // 3)
        draw.polygon([(tip_x, tip_y), (base_x, mid_y - 20), (base_x, mid_y + 20)], fill=fill)
        draw.line([(base_x, mid_y - 20), (tip_x, tip_y), (base_x, mid_y + 20)], fill=outline, width=outline_width)
    else:
        mid_x = (bx0 + bx1) // 2
        base_y = by1 - max(4, radius // 4)
        draw.polygon([(tip_x, tip_y), (mid_x - 22, base_y), (mid_x + 22, base_y)], fill=fill)
        draw.line([(mid_x - 22, base_y), (tip_x, tip_y), (mid_x + 22, base_y)], fill=outline, width=outline_width)


def draw_mascot_narrator(
    canvas: Image.Image,
    mascot: Image.Image,
    speech: str,
    *,
    font: ImageFont.FreeTypeFont,
    strip_top: int,
    strip_bottom: int,
    bubble_fill: tuple[int, int, int] = BUBBLE_FILL,
    text_fill: tuple[int, int, int] = INK_BLACK,
    mascot_max_height: int = 320,
    margin: int = 52,
    gap: int = 28,
    center_in_strip: bool = False,
    strip_x0: int | None = None,
    strip_x1: int | None = None,
) -> Image.Image:
    speech = (speech or "").strip()
    if mascot is None:
        return canvas

    base = canvas.convert("RGBA")
    draw = ImageDraw.Draw(base)
    strip_h = max(strip_bottom - strip_top, 120)
    sx0 = strip_x0 if strip_x0 is not None else margin
    sx1 = strip_x1 if strip_x1 is not None else CANVAS_WIDTH - margin
    strip_inner_w = max(200, sx1 - sx0)

    target_h = min(mascot_max_height, int(strip_h * 0.92))
    target_w = int(target_h * 1.38)
    icon = mascot.copy()
    icon.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)

    if not speech:
        mx = sx0 + (strip_inner_w - icon.width) // 2
        my = strip_top + (strip_h - icon.height) // 2
        base.paste(icon, (mx, my), icon)
        return base

    pad_x, pad_y = 36, 28
    line_h = int(font.size * 1.32)
    max_bubble_w = max(140, strip_inner_w - icon.width - gap - 24)

    lines = _wrap_speech_lines(draw, speech, font, max_bubble_w - pad_x * 2)
    if not lines:
        mx = sx0 + (strip_inner_w - icon.width) // 2
        my = strip_top + (strip_h - icon.height) // 2
        base.paste(icon, (mx, my), icon)
        return base

    bubble_w = min(
        max_bubble_w,
        max(int(draw.textlength(line, font=font)) for line in lines) + pad_x * 2,
    )
    bubble_h = pad_y * 2 + line_h * len(lines)
    bubble_h = min(bubble_h, strip_h - 24)

    group_w = icon.width + gap + bubble_w
    if center_in_strip:
        mx = sx0 + max(0, (strip_inner_w - group_w) // 2)
    else:
        mx = sx0
    mx = max(sx0, min(mx, sx1 - group_w))
    my = strip_top + max(0, (strip_h - icon.height) // 2)

    bubble_x0 = mx + icon.width + gap
    bx0 = bubble_x0
    bx1 = bx0 + bubble_w
    by0 = strip_top + max(0, (strip_h - bubble_h) // 2)
    by1 = by0 + bubble_h
    if by1 > strip_bottom - 8:
        by1 = strip_bottom - 8
        by0 = by1 - bubble_h
    if by0 < strip_top + 8:
        by0 = strip_top + 8
        by1 = by0 + bubble_h
    bx1 = min(bx1, sx1 - 8)
    tail_tip = (mx + icon.width - 6, my + icon.height // 2)

    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle((bx0 + 4, by0 + 6, bx1 + 4, by1 + 6), radius=30, fill=(0, 0, 0, 50))
    base = Image.alpha_composite(base, shadow)
    draw = ImageDraw.Draw(base)

    draw_classic_speech_bubble(
        draw,
        bx0=bx0,
        by0=by0,
        bx1=bx1,
        by1=by1,
        tail_tip=tail_tip,
        tail_from_side="left",
        fill=bubble_fill,
        outline=BUBBLE_OUTLINE,
        radius=30,
    )

    ty = by0 + pad_y
    for line in lines:
        draw.text((bx0 + pad_x, ty), line, font=font, fill=text_fill)
        ty += line_h

    base.paste(icon, (mx, my), icon)
    return base
