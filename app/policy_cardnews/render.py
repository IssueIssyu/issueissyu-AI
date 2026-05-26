from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.policy_cardnews.constants import CANVAS_HEIGHT, CANVAS_WIDTH
from app.policy_cardnews.copy import (
    compact_cardnews_slides,
    is_slide_empty,
    normalize_slide_copy,
)
from app.policy_cardnews.images import download_cardnews_images
from app.policy_cardnews.mascot import pick_mascot, pick_pin_mascot
from app.policy_cardnews.slides import parse_cardnews_slides_json
from app.policy_cardnews.template import (
    LAYOUT_COVER,
    MASCOT_LAYOUTS,
    apply_deck_template_theme,
    build_template_context,
    normalize_to_template_slide,
    render_template_slide,
    resolve_template_palette,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class SlideRenderContext:
    slide: dict[str, Any]
    minister: str
    hero_image: Image.Image | None
    mascot: Image.Image | None
    mascot_name: str
    slide_total: int
    source_url: str = ""


def _to_handoff_path(path: Path) -> str:
    try:
        return path.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_slide_copy(slide: dict[str, Any]) -> dict[str, Any]:
    return normalize_slide_copy(slide)


def _render_slide_image(*, ctx: SlideRenderContext, background: Image.Image) -> Image.Image:
    slide_no = int(ctx.slide.get("slide") or 1)
    slide = normalize_to_template_slide(ctx.slide, index=slide_no, total=ctx.slide_total)
    palette = resolve_template_palette(str(slide.get("template_palette") or "royal_blue"))
    tmpl_ctx = build_template_context(
        slide,
        slide_no=slide_no,
        slide_total=ctx.slide_total,
        minister=ctx.minister,
        mascot=ctx.mascot,
        source_url=ctx.source_url,
        palette=palette,
        hero_image=ctx.hero_image,
        use_cover_image=slide_no == 1 and ctx.hero_image is not None,
    )
    return render_template_slide(tmpl_ctx)


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

    from app.utils.policy_news_parse import enrich_cover_image_urls, merge_policy_image_urls

    urls = merge_policy_image_urls(
        original_image_urls=image_urls,
        cardnews_image_urls=None,
    )
    if background_image_url and background_image_url not in urls:
        urls.insert(0, background_image_url)
    urls = await enrich_cover_image_urls(urls, source_url=source_url)
    photos = await download_cardnews_images(urls[:8], referer=source_url or "https://www.korea.kr")

    rng = random.Random()
    prepared = [_normalize_slide_copy(s) for s in slides]
    prepared = apply_deck_template_theme(prepared, rng=rng, contentid=contentid)
    prepared = compact_cardnews_slides(prepared)
    from app.policy_cardnews.terms import enrich_cardnews_terminology

    prepared = enrich_cardnews_terminology(prepared, pin_content=pin_content)
    prepared = [_normalize_slide_copy(s) for s in prepared]
    slides_to_render = [s for s in prepared if not is_slide_empty(s)]
    if not slides_to_render:
        raise ValueError("렌더링할 카드뉴스 슬라이드가 없습니다 (내용 부족)")

    slide_total = len(slides_to_render)
    saved_paths: list[str] = []
    for index, slide in enumerate(slides_to_render, start=1):
        slide = dict(slide)
        slide["slide"] = index
        slide_no = index
        layout = str(slide.get("layout_type") or LAYOUT_COVER)
        is_cover = layout == LAYOUT_COVER or slide_no == 1
        is_cta = slide_no == slide_total or layout == "template_cta"

        mascot_name = ""
        mascot = None
        hero: Image.Image | None = None

        if is_cover:
            slide["use_image"] = True
            if photos:
                hero = photos[0]
            else:
                mascot_pick = pick_mascot(rng)
                if mascot_pick:
                    mascot_name, mascot = mascot_pick[0], mascot_pick[1]
                else:
                    logger.warning("표지: 원문 사진·마스코트를 모두 사용할 수 없습니다")
        else:
            hero = photos[index % len(photos)] if photos else None
            if is_cta:
                mascot_pick = pick_pin_mascot(rng)
            elif layout in MASCOT_LAYOUTS:
                mascot_pick = pick_mascot(rng)
            else:
                mascot_pick = None
            if mascot_pick:
                mascot_name, mascot = mascot_pick[0], mascot_pick[1]

        palette = resolve_template_palette(str(slide.get("template_palette") or "royal_blue"))
        ctx = SlideRenderContext(
            slide=slide,
            minister=minister,
            hero_image=hero,
            mascot=mascot,
            mascot_name=mascot_name,
            slide_total=slide_total,
            source_url=source_url,
        )
        background = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), palette.outer)
        out_path = target_dir / f"slide_{slide_no:02d}.png"
        image = _render_slide_image(ctx=ctx, background=background)
        image.save(out_path, format="PNG")
        saved_paths.append(_to_handoff_path(out_path))

    return saved_paths


__all__ = [
    "parse_cardnews_slides_json",
    "render_policy_cardnews_slides",
    "save_slide_image_bytes",
]
