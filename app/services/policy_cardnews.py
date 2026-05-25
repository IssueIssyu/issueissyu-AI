from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.PolicyCardnewsImageService import PolicyCardnewsImageService
from app.services.prompts.policy_cardnews import (
    build_policy_cardnews_image_prompt,
    build_policy_cardnews_slide_prompt,
)
from app.utils.policy_cardnews_render import (
    parse_cardnews_slides_json,
    render_policy_cardnews_slides,
    save_slide_image_bytes,
)

logger = logging.getLogger(__name__)

POLICY_CARDNEWS_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "policy_cardnews"
)


async def _generate_with_image_model(
    *,
    image_service: PolicyCardnewsImageService,
    content_id: str,
    pin_title: str,
    minister: str,
    slides: list[dict[str, Any]],
    output_dir: Path,
) -> list[str]:
    saved_paths: list[str] = []
    total = len(slides)
    for index, slide in enumerate(slides, start=1):
        prompt = build_policy_cardnews_image_prompt(
            pin_title=pin_title,
            minister=minister,
            slide=slide,
            slide_index=index,
            slide_total=total,
        )
        image_bytes = await image_service.generate_slide_image_bytes(prompt=prompt)
        slide_no = int(slide.get("slide") or index)
        saved_paths.append(
            save_slide_image_bytes(
                contentid=content_id,
                slide_no=slide_no,
                image_bytes=image_bytes,
                output_dir=output_dir,
            )
        )
    return saved_paths


async def _generate_with_pillow(
    *,
    content_id: str,
    minister: str,
    slides: list[dict[str, Any]],
    output_dir: Path,
    image_urls: list[str],
    source_url: str = "",
    pin_content: str = "",
) -> list[str]:
    return await render_policy_cardnews_slides(
        contentid=content_id,
        slides=slides,
        output_dir=output_dir,
        minister=minister,
        image_urls=image_urls,
        source_url=source_url,
        pin_content=pin_content,
    )


async def generate_cardnews_image_paths(
    text_llm: IssuePinLLMService,
    *,
    row: dict,
    easy_read_content: str,
    output_dir: Path | None = None,
    image_service: PolicyCardnewsImageService | None = None,
) -> list[str]:
    content_id = str(row.get("contentid") or "").strip()
    if not content_id:
        return []

    existing = [str(url).strip() for url in (row.get("cardnews_image_urls") or []) if str(url).strip()]
    prompt = build_policy_cardnews_slide_prompt(
        pin_title=str(row.get("pin_title") or ""),
        pin_content=easy_read_content or str(row.get("pin_content") or ""),
        minister=str(row.get("minister") or ""),
    )
    raw = await text_llm.generate_pin_text(prompt=prompt)
    slides = parse_cardnews_slides_json(raw)

    target_dir = output_dir or POLICY_CARDNEWS_OUTPUT_DIR
    pin_title = str(row.get("pin_title") or "")
    minister = str(row.get("minister") or "")
    image_urls = list(row.get("original_image_urls") or row.get("image_urls") or [])
    cardnews_urls = [str(u).strip() for u in (row.get("cardnews_image_urls") or []) if str(u).strip()]
    for url in cardnews_urls:
        if url.startswith(("http://", "https://")) and url not in image_urls:
            image_urls.append(url)
    if image_urls and slides:
        first = dict(slides[0])
        first["use_image"] = True
        slides[0] = first

    if settings.policy_cardnews_use_image_model:
        img_service = image_service or PolicyCardnewsImageService.from_settings()
        try:
            generated = await _generate_with_image_model(
                image_service=img_service,
                content_id=content_id,
                pin_title=pin_title,
                minister=minister,
                slides=slides,
                output_dir=target_dir,
            )
        except Exception:
            if not settings.policy_cardnews_pillow_fallback:
                raise
            logger.exception(
                "카드뉴스 이미지 모델 생성 실패 → Pillow 폴백 contentid=%s",
                content_id,
            )
            generated = await _generate_with_pillow(
                content_id=content_id,
                minister=minister,
                slides=slides,
                output_dir=target_dir,
                image_urls=image_urls,
                source_url=str(row.get("source_url") or ""),
                pin_content=easy_read_content or str(row.get("pin_content") or ""),
            )
    else:
        generated = await _generate_with_pillow(
            content_id=content_id,
            minister=minister,
            slides=slides,
            output_dir=target_dir,
            image_urls=image_urls,
            source_url=str(row.get("source_url") or ""),
            pin_content=easy_read_content or str(row.get("pin_content") or ""),
        )

    return existing + generated
