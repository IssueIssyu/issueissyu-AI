from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TypedDict

from app.core.config import settings
from app.policy_cardnews import (
    parse_cardnews_slides_json,
    render_policy_cardnews_slides,
    save_slide_image_bytes,
)
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.PolicyCardnewsImageService import PolicyCardnewsImageService
from app.services.prompts.policy_cardnews import (
    build_policy_cardnews_image_prompt,
    build_policy_cardnews_slide_prompt,
)
from app.utils.S3Util import S3Util

logger = logging.getLogger(__name__)

POLICY_CARDNEWS_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "policy_cardnews"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]


class CardnewsS3Image(TypedDict):
    key: str
    url: str


def cleanup_local_cardnews_dir(content_id: str) -> None:
    target = POLICY_CARDNEWS_OUTPUT_DIR / str(content_id or "").strip()
    if not target.is_dir():
        return
    import shutil

    shutil.rmtree(target, ignore_errors=True)
    logger.debug("로컬 카드뉴스 디렉터리 삭제: %s", target)


def _maybe_cleanup_local_cardnews(content_id: str) -> None:
    if not settings.policy_cardnews_keep_local_files:
        cleanup_local_cardnews_dir(content_id)


def _slide_object_key(content_id: str, slide_no: int) -> str:
    prefix = settings.policy_cardnews_s3_prefix.strip("/")
    return f"{prefix}/{content_id}/slide_{slide_no:02d}.png"


async def _upload_slide_bytes(
    s3_util: S3Util,
    *,
    content_id: str,
    slide_no: int,
    image_bytes: bytes,
) -> CardnewsS3Image:
    key = _slide_object_key(content_id, slide_no)
    result = await s3_util.upload_bytes(
        image_bytes,
        filename=f"slide_{slide_no:02d}.png",
        content_type="image/png",
        object_key=key,
    )
    return {"key": result["key"], "url": result["url"]}


async def _upload_local_handoff_path(
    s3_util: S3Util,
    *,
    content_id: str,
    handoff_path: str,
) -> CardnewsS3Image:
    rel = handoff_path.strip().lstrip("/")
    local_path = _REPO_ROOT / rel
    if not local_path.is_file():
        raise FileNotFoundError(f"카드뉴스 로컬 파일 없음: {local_path}")
    slide_name = local_path.stem
    slide_no = 1
    if slide_name.startswith("slide_"):
        try:
            slide_no = int(slide_name.split("_", 1)[1])
        except ValueError:
            slide_no = 1
    image_bytes = local_path.read_bytes()
    return await _upload_slide_bytes(
        s3_util,
        content_id=content_id,
        slide_no=slide_no,
        image_bytes=image_bytes,
    )


async def _generate_slide_bytes_with_image_model(
    *,
    image_service: PolicyCardnewsImageService,
    content_id: str,
    pin_title: str,
    minister: str,
    slides: list[dict[str, Any]],
) -> list[tuple[int, bytes]]:
    out: list[tuple[int, bytes]] = []
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
        out.append((slide_no, image_bytes))
    return out


async def _generate_local_paths_with_pillow(
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


async def generate_cardnews_s3_images(
    text_llm: IssuePinLLMService,
    *,
    row: dict,
    easy_read_content: str,
    s3_util: S3Util,
    output_dir: Path | None = None,
    image_service: PolicyCardnewsImageService | None = None,
) -> list[CardnewsS3Image]:
    content_id = str(row.get("contentid") or "").strip()
    if not content_id:
        return []

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
    from app.utils.policy_news_parse import enrich_cover_image_urls, merge_policy_image_urls

    source_url = str(row.get("source_url") or "")
    image_urls = merge_policy_image_urls(
        original_image_urls=row.get("original_image_urls"),
        cardnews_image_urls=row.get("cardnews_image_urls"),
    )
    if not image_urls:
        image_urls = [str(u).strip() for u in (row.get("image_urls") or []) if str(u).strip()]
    image_urls = await enrich_cover_image_urls(image_urls, source_url=source_url)
    if image_urls and slides:
        first = dict(slides[0])
        first["use_image"] = True
        slides[0] = first

    uploaded: list[CardnewsS3Image] = []

    if settings.policy_cardnews_use_image_model:
        img_service = image_service or PolicyCardnewsImageService.from_settings()
        try:
            slide_bytes_list = await _generate_slide_bytes_with_image_model(
                image_service=img_service,
                content_id=content_id,
                pin_title=pin_title,
                minister=minister,
                slides=slides,
            )
            for slide_no, image_bytes in slide_bytes_list:
                if settings.policy_cardnews_keep_local_files:
                    save_slide_image_bytes(
                        contentid=content_id,
                        slide_no=slide_no,
                        image_bytes=image_bytes,
                        output_dir=target_dir,
                    )
                uploaded.append(
                    await _upload_slide_bytes(
                        s3_util,
                        content_id=content_id,
                        slide_no=slide_no,
                        image_bytes=image_bytes,
                    ),
                )
        except Exception:
            if not settings.policy_cardnews_pillow_fallback:
                raise
            logger.exception(
                "카드뉴스 이미지 모델 생성 실패로 Pillow 폴백 contentid=%s",
                content_id,
            )
            local_paths = await _generate_local_paths_with_pillow(
                content_id=content_id,
                minister=minister,
                slides=slides,
                output_dir=target_dir,
                image_urls=image_urls,
                source_url=source_url,
                pin_content=easy_read_content or str(row.get("pin_content") or ""),
            )
            for path in local_paths:
                uploaded.append(
                    await _upload_local_handoff_path(
                        s3_util,
                        content_id=content_id,
                        handoff_path=path,
                    ),
                )
    else:
        local_paths = await _generate_local_paths_with_pillow(
            content_id=content_id,
            minister=minister,
            slides=slides,
            output_dir=target_dir,
            image_urls=image_urls,
            source_url=source_url,
            pin_content=easy_read_content or str(row.get("pin_content") or ""),
        )
        for path in local_paths:
            uploaded.append(
                await _upload_local_handoff_path(
                    s3_util,
                    content_id=content_id,
                    handoff_path=path,
                ),
            )

    if not settings.policy_cardnews_keep_local_files:
        _maybe_cleanup_local_cardnews(content_id)
    return uploaded


async def generate_cardnews_image_paths(
    text_llm: IssuePinLLMService,
    *,
    row: dict,
    easy_read_content: str,
    output_dir: Path | None = None,
    image_service: PolicyCardnewsImageService | None = None,
    s3_util: S3Util | None = None,
) -> list[str]:
    """하위 호환: S3 URL 문자열 목록만 반환."""
    s3 = s3_util or S3Util()
    images = await generate_cardnews_s3_images(
        text_llm,
        row=row,
        easy_read_content=easy_read_content,
        s3_util=s3,
        output_dir=output_dir,
        image_service=image_service,
    )
    return [img["url"] for img in images if img.get("url")]
