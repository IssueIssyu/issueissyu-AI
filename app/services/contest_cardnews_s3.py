from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

from anyio import to_thread

from app.core.config import settings
from app.services.contest_cardnews import CONTEST_CARDNEWS_OUTPUT_DIR, generate_contest_cardnews_paths
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.utils.S3Util import S3Util

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


class CardnewsS3Image(TypedDict):
    key: str
    url: str


def cleanup_local_cardnews_dir(content_id: str) -> None:
    normalized = str(content_id or "").strip()
    if not normalized:
        return
    target = CONTEST_CARDNEWS_OUTPUT_DIR / normalized
    if not target.is_dir():
        return
    import shutil

    shutil.rmtree(target, ignore_errors=True)
    logger.debug("로컬 카드뉴스 디렉터리 삭제: %s", target)


def _maybe_cleanup_local_cardnews(content_id: str) -> None:
    if not settings.contest_cardnews_keep_local_files:
        cleanup_local_cardnews_dir(content_id)


def _slide_object_key(content_id: str, slide_no: int) -> str:
    prefix = settings.contest_cardnews_s3_prefix.strip("/")
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
    local_path = Path(handoff_path)
    if not local_path.is_absolute():
        local_path = (_REPO_ROOT / handoff_path.strip().lstrip("/")).resolve()
    if not local_path.is_file():
        raise FileNotFoundError(f"카드뉴스 로컬 파일 없음: {local_path}")
    slide_name = local_path.stem
    slide_no = 1
    if slide_name.startswith("slide_"):
        try:
            slide_no = int(slide_name.split("_", 1)[1])
        except ValueError:
            slide_no = 1
    image_bytes = await to_thread.run_sync(local_path.read_bytes)
    return await _upload_slide_bytes(
        s3_util,
        content_id=content_id,
        slide_no=slide_no,
        image_bytes=image_bytes,
    )


async def upload_contest_cardnews_s3_images(
    text_llm: IssuePinLLMService,
    *,
    row: dict[str, Any],
    s3_util: S3Util,
    with_caption: bool = True,
    output_dir: Path | None = None,
) -> tuple[list[CardnewsS3Image], str]:
    """로컬 PNG 생성 후 S3 업로드."""
    cardnews_paths, caption = await generate_contest_cardnews_paths(
        text_llm,
        row=row,
        output_dir=output_dir,
        with_caption=with_caption,
    )
    if not cardnews_paths:
        raise ValueError("카드뉴스 이미지가 생성되지 않음")

    content_id = str(row.get("contentid") or "").strip()
    uploaded: list[CardnewsS3Image] = []
    for path in cardnews_paths:
        uploaded.append(
            await _upload_local_handoff_path(
                s3_util,
                content_id=content_id,
                handoff_path=path,
            ),
        )

    _maybe_cleanup_local_cardnews(content_id)
    return uploaded, caption
