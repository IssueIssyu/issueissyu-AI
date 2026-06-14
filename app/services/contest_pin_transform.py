from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.ContestPinDTO import ContestPinHandoffDTO, ContestPinTransformResult
from app.services.contest_cardnews_s3 import CardnewsS3Image, upload_contest_cardnews_s3_images
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.gemini_factory import build_issue_pin_llm_service
from app.utils.contest_images import pin_images_for_db_row
from app.utils.pin_content import append_source_link_to_pin_content
from app.utils.S3Util import S3Util
from rag.scripts.chunk_module import iter_jsonl, write_jsonl
from rag.scripts.fetch_linkareer_contests import CONTEST_DOCUMENTS_PATH, clean_contest_body, is_contest_row_expired

CONTEST_HANDOFF_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "contest_pins_for_db.jsonl"
)
CONTEST_SYNC_META_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "contest_sync_meta.json"
)


def parse_contest_api_id(row: dict[str, Any]) -> int | None:
    raw = row.get("contest_api_id") or row.get("contentid")
    if raw is None:
        return None
    text = str(raw).strip()
    if not text.isdigit():
        return None
    return int(text)


def row_content_id(row: dict[str, Any]) -> str:
    return str(row.get("contentid") or row.get("contest_api_id") or "").strip()


def load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [row for row in iter_jsonl(path) if isinstance(row, dict)]


def load_rows_by_content_id(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in load_jsonl_rows(path):
        content_id = row_content_id(row)
        if content_id:
            out[content_id] = row
    return out


def write_handoff_map(handoff_by_id: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    dst = path or CONTEST_HANDOFF_PATH
    write_jsonl(dst, list(handoff_by_id.values()))


def build_handoff_row(
    source: dict[str, Any],
    *,
    pin_content: str,
    cardnews_images: list[CardnewsS3Image] | None = None,
    cardnews_image_urls: list[str] | None = None,
) -> dict[str, Any]:
    content_id = row_content_id(source)
    contest_api_id = parse_contest_api_id(source)
    images = cardnews_images or []
    urls = cardnews_image_urls or [img["url"] for img in images if str(img.get("url") or "").strip()]
    source_url = (source.get("source_url") or "").strip()
    body = append_source_link_to_pin_content(pin_content, source_url)
    pin_images = pin_images_for_db_row(source)
    return {
        "contentid": content_id,
        "contest_api_id": contest_api_id,
        "title": (source.get("pin_title") or source.get("title") or "").strip(),
        "pin_content": body,
        "pin_images": pin_images,
        "cardnews_image_urls": [str(u).strip() for u in urls if str(u).strip()],
        "cardnews_images": images,
        "source_url": source_url,
        "event_start_time": source.get("event_start_time"),
        "event_end_time": source.get("event_end_time"),
        "host_org": (source.get("host_org") or "").strip(),
    }


async def transform_one_row(
    llm: IssuePinLLMService,
    row: dict[str, Any],
    *,
    s3_util: S3Util,
    with_caption: bool = True,
) -> dict[str, Any]:
    pin_title = str(row.get("pin_title") or "").strip()
    raw = clean_contest_body(
        str(row.get("pin_content_raw") or row.get("pin_content") or ""),
        pin_title=pin_title,
    )
    if not raw:
        raise ValueError("pin_content_raw가 비어 있음")

    cardnews_images, caption = await upload_contest_cardnews_s3_images(
        llm,
        row={**row, "pin_content_raw": raw},
        s3_util=s3_util,
        with_caption=with_caption,
    )
    pin_content = caption if caption else raw
    return build_handoff_row(
        row,
        pin_content=pin_content,
        cardnews_images=cardnews_images,
    )


def list_pending_transform_rows(
    documents: list[dict[str, Any]],
    handoff_by_id: dict[str, dict[str, Any]],
    *,
    db_contest_api_ids: set[int] | None = None,
    contentid: str | None = None,
) -> list[dict[str, Any]]:
    db_ids = db_contest_api_ids or set()
    cid_filter = (contentid or "").strip()
    pending: list[dict[str, Any]] = []
    for row in documents:
        content_id = row_content_id(row)
        if not content_id:
            continue
        if cid_filter and content_id != cid_filter:
            continue
        contest_id = parse_contest_api_id(row)
        if contest_id is not None and contest_id in db_ids:
            continue
        if is_contest_row_expired(row):
            continue
        if content_id in handoff_by_id:
            continue
        pending.append(row)
    return pending


def count_skipped_expired_transform_rows(
    documents: list[dict[str, Any]],
    handoff_by_id: dict[str, dict[str, Any]],
    *,
    db_contest_api_ids: set[int] | None = None,
    contentid: str | None = None,
) -> int:
    db_ids = db_contest_api_ids or set()
    cid_filter = (contentid or "").strip()
    count = 0
    for row in documents:
        content_id = row_content_id(row)
        if not content_id:
            continue
        if cid_filter and content_id != cid_filter:
            continue
        if not is_contest_row_expired(row):
            continue
        contest_id = parse_contest_api_id(row)
        if contest_id is not None and contest_id in db_ids:
            continue
        if content_id in handoff_by_id:
            continue
        count += 1
    return count


def count_pending_transform(
    documents: list[dict[str, Any]],
    handoff_by_id: dict[str, dict[str, Any]],
    *,
    db_contest_api_ids: set[int] | None = None,
) -> int:
    return len(
        list_pending_transform_rows(
            documents,
            handoff_by_id,
            db_contest_api_ids=db_contest_api_ids,
        ),
    )


async def transform_documents_jsonl(
    *,
    input_path: Path | None = None,
    output_path: Path | None = None,
    limit: int | None = None,
    model: str | None = None,
    s3_util: S3Util | None = None,
    db_contest_api_ids: set[int] | None = None,
    merge_handoff: bool = True,
    with_caption: bool = True,
    contentid: str | None = None,
) -> ContestPinTransformResult:
    src = input_path or CONTEST_DOCUMENTS_PATH
    dst = output_path or CONTEST_HANDOFF_PATH
    if not src.is_file():
        raise FileNotFoundError(
            f"원문 JSONL 없음: {src}. POST /contest-pins/crawl 을 먼저 실행하세요.",
        )

    documents = load_jsonl_rows(src)
    handoff_by_id = load_rows_by_content_id(dst) if merge_handoff else {}
    db_ids = db_contest_api_ids or set()
    pending = list_pending_transform_rows(
        documents,
        handoff_by_id,
        db_contest_api_ids=db_ids,
        contentid=contentid,
    )

    llm = build_issue_pin_llm_service(model=model)
    s3 = s3_util or S3Util()
    processed_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped_duplicate_count = 0
    skipped_expired_count = count_skipped_expired_transform_rows(
        documents,
        handoff_by_id,
        db_contest_api_ids=db_ids,
        contentid=contentid,
    )

    rows_to_process = pending if limit is None else pending[:limit]
    concurrency = min(settings.contest_transform_concurrency, len(rows_to_process) or 1)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _transform_row(row: dict[str, Any]) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
        content_id = row_content_id(row)
        async with semaphore:
            try:
                handoff_row = await transform_one_row(llm, row, s3_util=s3, with_caption=with_caption)
                return content_id, handoff_row, None
            except Exception as exc:
                return content_id, None, {
                    "contentid": content_id,
                    "pin_title": row.get("pin_title"),
                    "error": str(exc),
                }

    for content_id, handoff_row, err_row in await asyncio.gather(
        *(_transform_row(row) for row in rows_to_process),
    ):
        if handoff_row is not None and content_id:
            handoff_by_id[content_id] = handoff_row
            processed_rows.append(handoff_row)
        elif err_row is not None:
            errors.append(err_row)

    for row in documents:
        content_id = row_content_id(row)
        if not content_id or content_id in handoff_by_id:
            continue
        contest_id = parse_contest_api_id(row)
        if contest_id is not None and contest_id in db_ids:
            skipped_duplicate_count += 1

    write_handoff_map(handoff_by_id, dst)
    remaining_pending = count_pending_transform(
        documents,
        handoff_by_id,
        db_contest_api_ids=db_ids,
    )
    pins = [ContestPinHandoffDTO.from_row(item) for item in processed_rows]

    hint: str | None
    if processed_rows or handoff_by_id:
        hint = (
            f"이번 가공 {len(processed_rows)}건, handoff 총 {len(handoff_by_id)}건. "
            "카드뉴스는 텍스트·캐릭터만 사용(크롤 이미지 미포함)."
        )
    else:
        hint = "가공 성공 건이 없습니다. GEMINI_API_KEY·pin_content_raw를 확인하세요."

    return ContestPinTransformResult(
        input_path=str(src),
        output_path=str(dst),
        processed_count=len(processed_rows),
        error_count=len(errors),
        errors=errors,
        pins=pins,
        hint=hint,
        skipped_duplicate_count=skipped_duplicate_count,
        skipped_expired_count=skipped_expired_count,
        pending_count=len(pending),
        remaining_pending_count=remaining_pending,
    )


def load_handoff_from_jsonl(
    *,
    file_path: Path | None = None,
    limit: int | None = None,
) -> tuple[Path, list[ContestPinHandoffDTO], int]:
    path = file_path or CONTEST_HANDOFF_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"핸드오프 JSONL 없음: {path}. POST /contest-pins/cardnews 를 먼저 실행하세요.",
        )

    max_items = 500 if limit is None else min(limit, 500)
    pins: list[ContestPinHandoffDTO] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            pins.append(ContestPinHandoffDTO.from_row(json.loads(line)))

    total_in_file = len(pins)
    return path, pins[:max_items], total_in_file
