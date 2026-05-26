from __future__ import annotations

from PIL import Image, ImageDraw


def paste_rounded_image_fit(
    canvas: Image.Image,
    photo: Image.Image,
    *,
    box: tuple[int, int, int, int],
    radius: int = 24,
    plate_fill: tuple[int, int, int] = (248, 250, 252),
) -> Image.Image:
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
