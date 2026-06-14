from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.contest_cardnews.template import (
    LAYOUT_COVER,
    LAYOUT_CTA,
    apply_deck_palette,
    normalize_contest_slide,
    render_contest_slide,
    resolve_palette,
)
from app.contest_cardnews.copy import (
    is_contest_slide_empty,
    normalize_contest_slide_copy,
    prepare_contest_slides,
)
from app.policy_cardnews.mascot import pick_mascot, pick_pin_mascot

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ContestSlideRenderContext:
    slide: dict[str, Any]
    host_org: str
    mascot: Image.Image | None
    mascot_name: str
    slide_total: int
    source_url: str = ""


def _to_handoff_path(path: Path) -> str:
    try:
        return path.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _render_slide_image(*, ctx: ContestSlideRenderContext) -> Image.Image:
    slide_no = int(ctx.slide.get("slide") or 1)
    slide = normalize_contest_slide(ctx.slide, index=slide_no, total=ctx.slide_total)
    palette = resolve_palette(str(slide.get("template_palette") or "pastel_mint"))
    return render_contest_slide(
        slide,
        palette=palette,
        mascot=ctx.mascot,
        source_url=ctx.source_url,
    )


async def render_contest_cardnews_slides(
    *,
    contentid: str,
    slides: list[dict[str, Any]],
    output_dir: Path,
    host_org: str = "",
    source_url: str = "",
) -> list[str]:
    """공모전 전용 브라우저형 템플릿 + 캐릭터 PNG (정책 템플릿·크롤 이미지 미사용)."""
    target_dir = output_dir / contentid
    target_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(contentid)
    prepared = prepare_contest_slides(slides)
    for row in prepared:
        row["use_image"] = False
    prepared = apply_deck_palette(prepared, rng=rng, contentid=contentid)
    prepared = [normalize_contest_slide_copy(s) for s in prepared]
    slides_to_render = [s for s in prepared if not is_contest_slide_empty(s)]
    if not slides_to_render:
        raise ValueError("렌더링할 카드뉴스 슬라이드가 없습니다 (내용 부족)")

    slide_total = len(slides_to_render)
    saved_paths: list[str] = []

    for index, slide in enumerate(slides_to_render, start=1):
        slide = dict(slide)
        slide["slide"] = index
        slide["use_image"] = False
        layout = str(slide.get("layout_type") or LAYOUT_COVER)
        is_cover = layout == LAYOUT_COVER or index == 1
        is_cta = index == slide_total or layout == LAYOUT_CTA

        mascot_name = ""
        mascot: Image.Image | None = None
        if is_cover:
            mascot_pick = pick_mascot(rng)
            if mascot_pick:
                mascot_name, mascot = mascot_pick[0], mascot_pick[1]
        elif is_cta:
            mascot_pick = pick_pin_mascot(rng)
            if mascot_pick:
                mascot_name, mascot = mascot_pick[0], mascot_pick[1]
        ctx = ContestSlideRenderContext(
            slide=slide,
            host_org=host_org,
            mascot=mascot,
            mascot_name=mascot_name,
            slide_total=slide_total,
            source_url=source_url,
        )
        out_path = target_dir / f"slide_{index:02d}.png"
        image = _render_slide_image(ctx=ctx)
        image.save(out_path, format="PNG")
        saved_paths.append(_to_handoff_path(out_path))
        if mascot_name:
            logger.info("공모전 카드뉴스 slide_%02d 캐릭터: %s", index, mascot_name)

    return saved_paths
