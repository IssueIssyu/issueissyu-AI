from __future__ import annotations

import random
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350


@dataclass(frozen=True)
class SlideVariation:
    hero_height: int = 500
    cover_mode: str = "hero_band"  # hero_band | hero_rounded | typo_only
    info_style: str = "list"  # list | cards
    quote_align: str = "left"  # left | center
    photo_radius: int = 32


def apply_blurred_cover_background(
    canvas: Image.Image,
    photo: Image.Image,
    *,
    blur_radius: int = 22,
    dim_alpha: int = 100,
) -> Image.Image:
    # 인스타 표지용 — 전체 블러 배경 (레퍼런스 1)
    base = canvas.convert("RGBA")
    bg = photo.copy().convert("RGBA")
    bg = bg.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    dim = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (240, 246, 255, dim_alpha))
    bg = Image.alpha_composite(bg, dim)
    return Image.alpha_composite(bg, base)


def pick_slide_variation(rng: random.Random, *, layout: str) -> SlideVariation:
    if layout == "cover_big_typo":
        return SlideVariation(
            hero_height=rng.choice([280, 320, 360]),
            cover_mode="blur_bg",
        )
    if layout == "info_blocks":
        return SlideVariation(info_style="cards")
    if layout == "quote_focus":
        return SlideVariation(quote_align=rng.choice(["left", "center"]))
    if layout == "image_split":
        return SlideVariation(
            hero_height=rng.choice([480, 540, 600]),
            photo_radius=rng.choice([24, 32, 40]),
        )
    return SlideVariation()


def paste_hero_band(
    canvas: Image.Image,
    photo: Image.Image,
    *,
    y0: int,
    height: int,
) -> Image.Image:
    base = canvas.convert("RGBA")
    band = photo.copy().convert("RGBA")
    src_w, src_h = band.size
    target_ratio = CANVAS_WIDTH / height
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        band = band.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = max(0, (src_h - new_h) // 2)
        band = band.crop((0, top, src_w, top + new_h))
    band = band.resize((CANVAS_WIDTH, height), Image.Resampling.LANCZOS)
    base.paste(band, (0, y0))

    fade = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(fade)
    fade_end = min(y0 + height + 48, base.size[1])
    for y in range(y0, fade_end):
        ratio = (y - y0) / max(height, 1)
        alpha = int(min(255, 200 * ratio**1.1))
        draw.line([(0, y), (base.size[0], y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(base, fade)


def paste_hero_top(
    canvas: Image.Image,
    photo: Image.Image,
    *,
    height: int,
) -> Image.Image:
    base = canvas.convert("RGBA")
    band = photo.copy().convert("RGBA")
    src_w, src_h = band.size
    target_ratio = CANVAS_WIDTH / height
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        band = band.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = max(0, (src_h - new_h) // 2)
        band = band.crop((0, top, src_w, top + new_h))
    band = band.resize((CANVAS_WIDTH, height), Image.Resampling.LANCZOS)

    base.paste(band, (0, 0))

    fade = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(fade)
    fade_h = min(height + 80, base.size[1])
    for y in range(fade_h):
        alpha = int(min(255, 180 * (y / max(fade_h - 1, 1)) ** 1.2))
        draw.line([(0, y), (base.size[0], y)], fill=(0, 0, 0, alpha))
    base = Image.alpha_composite(base, fade)
    return base


def paste_rounded_image_fit(
    canvas: Image.Image,
    photo: Image.Image,
    *,
    box: tuple[int, int, int, int],
    radius: int = 24,
    plate_fill: tuple[int, int, int] = (248, 250, 252),
) -> Image.Image:
    # 사진 전체가 보이도록 비율 유지·중앙 배치 (잘림 없음)
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return canvas

    thumb = photo.copy().convert("RGBA")
    tw, th = thumb.size
    if tw <= 0 or th <= 0:
        return canvas

    scale = min(w / tw, h / th)
    nw = max(1, int(tw * scale))
    nh = max(1, int(th * scale))
    thumb = thumb.resize((nw, nh), Image.Resampling.LANCZOS)

    base = canvas.convert("RGBA")
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x0 + 4, y0 + 6, x1 + 4, y1 + 6),
        radius=radius,
        fill=(0, 0, 0, 50),
    )
    base = Image.alpha_composite(base, shadow)

    plate = Image.new("RGBA", (w, h), (*plate_fill, 255))
    plate_mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(plate_mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    base.paste(plate, (x0, y0), plate_mask)

    px = x0 + (w - nw) // 2
    py = y0 + (h - nh) // 2
    base.paste(thumb, (px, py), thumb)
    return base


def paste_rounded_image(
    canvas: Image.Image,
    photo: Image.Image,
    *,
    box: tuple[int, int, int, int],
    radius: int = 24,
) -> Image.Image:
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return canvas

    thumb = photo.copy().convert("RGBA")
    tw, th = thumb.size
    ratio = w / h
    if tw / th > ratio:
        nw = int(th * ratio)
        left = (tw - nw) // 2
        thumb = thumb.crop((left, 0, left + nw, th))
    else:
        nh = int(tw / ratio)
        top = max(0, (th - nh) // 2)
        thumb = thumb.crop((0, top, tw, top + nh))
    thumb = thumb.resize((w, h), Image.Resampling.LANCZOS)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)

    base = canvas.convert("RGBA")
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x0 + 4, y0 + 6, x1 + 4, y1 + 6),
        radius=radius,
        fill=(0, 0, 0, 60),
    )
    base = Image.alpha_composite(base, shadow)
    base.paste(thumb, (x0, y0), mask)
    return base


def apply_soft_photo_wash(canvas: Image.Image, photo: Image.Image, *, opacity: float = 0.18) -> Image.Image:
    base = canvas.convert("RGBA")
    wash = photo.copy().convert("RGBA")
    wash = wash.resize(base.size, Image.Resampling.LANCZOS)
    wash = wash.filter(ImageFilter.GaussianBlur(radius=24))
    alpha = int(max(0, min(255, 255 * opacity)))
    wash.putalpha(alpha)
    return Image.alpha_composite(base, wash)
