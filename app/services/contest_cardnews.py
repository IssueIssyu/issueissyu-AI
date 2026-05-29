from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.contest_cardnews import render_contest_cardnews_slides
from app.contest_cardnews.slides import parse_contest_cardnews_slides_json
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.prompts.contest_cardnews import (
    build_contest_cardnews_caption_prompt,
    build_contest_cardnews_slide_prompt,
)
from rag.scripts.fetch_linkareer_contests import clean_contest_body

logger = logging.getLogger(__name__)

CONTEST_CARDNEWS_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "contest_cardnews"
)


async def generate_contest_cardnews_paths(
    text_llm: IssuePinLLMService,
    *,
    row: dict[str, Any],
    output_dir: Path | None = None,
    with_caption: bool = True,
) -> tuple[list[str], str]:
    """크롤 본문 → Gemini 슬라이드 JSON → 공모전 전용 브라우저 템플릿 PNG."""
    content_id = str(row.get("contentid") or "").strip()
    if not content_id:
        return [], ""

    pin_title = str(row.get("pin_title") or "").strip()
    host_org = str(row.get("host_org") or "").strip()
    source_url = str(row.get("source_url") or "").strip()
    raw = clean_contest_body(
        str(row.get("pin_content_raw") or row.get("pin_content") or ""),
        pin_title=pin_title,
    )
    if not raw:
        raise ValueError("pin_content_raw가 비어 있음")

    slide_prompt = build_contest_cardnews_slide_prompt(
        pin_title=pin_title,
        pin_content_raw=raw,
        host_org=host_org,
        event_start_time=row.get("event_start_time"),
        event_end_time=row.get("event_end_time"),
        source_url=source_url,
    )
    raw_slides = await text_llm.generate_pin_text(prompt=slide_prompt)
    slides = parse_contest_cardnews_slides_json(raw_slides)

    target_dir = output_dir or CONTEST_CARDNEWS_OUTPUT_DIR
    paths = await render_contest_cardnews_slides(
        contentid=content_id,
        slides=slides,
        output_dir=target_dir,
        host_org=host_org,
        source_url=source_url,
    )

    caption = ""
    if with_caption:
        cap_prompt = build_contest_cardnews_caption_prompt(
            pin_title=pin_title,
            pin_content_raw=raw,
            host_org=host_org,
            source_url=source_url,
        )
        try:
            caption = (await text_llm.generate_pin_text(prompt=cap_prompt)).strip()
        except Exception:
            logger.exception("공모전 캡션 생성 실패 contentid=%s", content_id)

    return paths, caption
