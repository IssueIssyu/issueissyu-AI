from __future__ import annotations

from typing import Any

from PIL import ImageDraw

from app.contest_cardnews.constants import CHROME_HEIGHT, INK_SOFT
from app.contest_cardnews.template.palette import ContestPalette

_TRAFFIC = ((235, 120, 110), (248, 210, 100), (130, 198, 130))


def draw_browser_chrome(
    draw: ImageDraw.ImageDraw,
    white_rect: tuple[int, int, int, int],
    palette: ContestPalette,
) -> int:
    """흰 카드 상단에 브라우저 UI. 반환: 콘텐츠 시작 y."""
    wx0, wy0, wx1, _wy1 = white_rect
    w = wx1 - wx0
    title_h = 44
    nav_h = CHROME_HEIGHT - title_h

    draw.rectangle((wx0, wy0, wx1, wy0 + title_h), fill=palette.chrome)
    dot_y = wy0 + title_h // 2
    for i, color in enumerate(_TRAFFIC):
        cx = wx0 + 22 + i * 22
        draw.ellipse((cx - 6, dot_y - 6, cx + 6, dot_y + 6), fill=color)

    tab_x0 = wx0 + w // 2 - 70
    tab_y0 = wy0 + 10
    draw.rounded_rectangle(
        (tab_x0, tab_y0, tab_x0 + 140, wy0 + title_h - 4),
        radius=10,
        fill=(255, 255, 255),
    )
    draw.text((tab_x0 + 118, tab_y0 + 6), "×", fill=INK_SOFT)

    nav_y0 = wy0 + title_h
    draw.rectangle((wx0, nav_y0, wx1, nav_y0 + nav_h), fill=(248, 250, 252))
    bar_y0 = nav_y0 + 12
    bar_h = nav_h - 24
    bar_x0 = wx0 + 88
    bar_x1 = wx1 - 52
    draw.rounded_rectangle(
        (bar_x0, bar_y0, bar_x1, bar_y0 + bar_h),
        radius=bar_h // 2,
        fill=(255, 255, 255),
        outline=palette.panel_border,
        width=2,
    )

    icon_x = wx0 + 18
    for dx in (0, 22, 44):
        _draw_nav_icon(draw, icon_x + dx, nav_y0 + nav_h // 2, palette.chrome_dark)
    draw.ellipse(
        (bar_x0 + 14, bar_y0 + bar_h // 2 - 7, bar_x0 + 28, bar_y0 + bar_h // 2 + 7),
        fill=palette.accent,
    )
    menu_x = wx1 - 36
    for row in range(3):
        cy = nav_y0 + 16 + row * 10
        draw.ellipse((menu_x, cy, menu_x + 6, cy + 6), fill=INK_SOFT)

    return wy0 + CHROME_HEIGHT


def _draw_nav_icon(draw: ImageDraw.ImageDraw, x: int, cy: int, fill: tuple[int, int, int]) -> None:
    draw.polygon([(x, cy), (x + 8, cy - 5), (x + 8, cy + 5)], fill=fill)
    draw.polygon([(x + 14, cy), (x + 6, cy - 5), (x + 6, cy + 5)], fill=fill)

