from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContestPalette:
    name: str
    outer: tuple[int, int, int]
    chrome: tuple[int, int, int]
    chrome_dark: tuple[int, int, int]
    accent: tuple[int, int, int]
    panel: tuple[int, int, int]
    panel_border: tuple[int, int, int]


CONTEST_PALETTES: dict[str, ContestPalette] = {
    "pastel_mint": ContestPalette(
        "pastel_mint",
        outer=(198, 228, 208),
        chrome=(156, 205, 168),
        chrome_dark=(108, 158, 122),
        accent=(72, 138, 98),
        panel=(232, 246, 236),
        panel_border=(156, 205, 168),
    ),
    "pastel_pink": ContestPalette(
        "pastel_pink",
        outer=(255, 218, 228),
        chrome=(245, 175, 195),
        chrome_dark=(210, 120, 148),
        accent=(198, 88, 118),
        panel=(255, 238, 242),
        panel_border=(245, 175, 195),
    ),
    "pastel_lavender": ContestPalette(
        "pastel_lavender",
        outer=(222, 214, 248),
        chrome=(188, 172, 230),
        chrome_dark=(140, 118, 198),
        accent=(108, 82, 178),
        panel=(238, 232, 252),
        panel_border=(188, 172, 230),
    ),
    "pastel_peach": ContestPalette(
        "pastel_peach",
        outer=(255, 228, 208),
        chrome=(248, 188, 148),
        chrome_dark=(210, 138, 88),
        accent=(198, 108, 58),
        panel=(255, 242, 230),
        panel_border=(248, 188, 148),
    ),
    "pastel_sky": ContestPalette(
        "pastel_sky",
        outer=(208, 232, 252),
        chrome=(148, 192, 232),
        chrome_dark=(88, 142, 198),
        accent=(58, 118, 188),
        panel=(228, 242, 255),
        panel_border=(148, 192, 232),
    ),
    "pastel_lemon": ContestPalette(
        "pastel_lemon",
        outer=(255, 248, 198),
        chrome=(238, 218, 118),
        chrome_dark=(198, 168, 58),
        accent=(168, 138, 28),
        panel=(255, 252, 228),
        panel_border=(238, 218, 118),
    ),
}


def palette_names() -> list[str]:
    return list(CONTEST_PALETTES.keys())


def resolve_palette(name: str) -> ContestPalette:
    key = (name or "pastel_mint").strip()
    return CONTEST_PALETTES.get(key, CONTEST_PALETTES["pastel_mint"])


def apply_deck_palette(
    slides: list[dict[str, Any]],
    *,
    rng: random.Random,
    contentid: str = "",
) -> list[dict[str, Any]]:
    deck_rng = random.Random(contentid) if contentid else rng
    names = palette_names()
    palette = ""
    for slide in slides:
        candidate = str(slide.get("template_palette") or "").strip()
        if candidate in CONTEST_PALETTES:
            palette = candidate
            break
    if not palette:
        palette = deck_rng.choice(names)
    out: list[dict[str, Any]] = []
    for slide in slides:
        row = dict(slide)
        row["template_palette"] = palette
        out.append(row)
    return out
