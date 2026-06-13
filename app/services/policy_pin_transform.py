from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.PolicyPinDTO import PolicyPinHandoffDTO, PolicyPinTransformResult
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.gemini_retry import parse_gemini_model_list
from app.services.policy_cardnews import CardnewsS3Image, generate_cardnews_s3_images
from app.services.prompts.policy_pin import build_policy_easy_read_prompt
from app.utils.S3Util import S3Util
from rag.scripts.chunk_module import iter_jsonl, write_jsonl

POLICY_DOCUMENTS_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "policy_documents.jsonl"
)
POLICY_HANDOFF_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "policy_pins_for_db.jsonl"
)
POLICY_SYNC_META_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "policy_sync_meta.json"
)


def append_source_link_to_pin_content(body: str, source_url: str) -> str:
    """가공 본문 끝에 원문 기사 URL을 붙인다 (중복 방지)."""
    text = (body or "").strip()
    url = (source_url or "").strip()
    if not url or not text:
        return text or url

    if url in text:
        return text

    normalized = url.rstrip("/")
    for line in text.splitlines():
        line = line.strip()
        if line == url or line.rstrip("/") == normalized:
            return text
        if line.startswith("http") and normalized in line:
            return text

    return f"{text}\n\n원문 기사: {url}"


def parse_policy_api_id(row: dict[str, Any]) -> int | None:
    raw = row.get("policy_api_id") or row.get("contentid")
    if raw is None:
        return None
    text = str(raw).strip()
    if not text.isdigit():
        return None
    return int(text)


def row_content_id(row: dict[str, Any]) -> str:
    return str(row.get("contentid") or row.get("policy_api_id") or "").strip()


def row_raw_content(row: dict[str, Any]) -> str:
    return (row.get("pin_content_raw") or row.get("pin_content") or row.get("text") or "").strip()


def normalize_raw_for_compare(text: str) -> str:
    return " ".join((text or "").split()).strip()


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


def merge_documents(
    existing: dict[str, dict[str, Any]],
    new_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = dict(existing)
    for row in new_rows:
        content_id = row_content_id(row)
        if content_id:
            merged[content_id] = row
    return list(merged.values())


def write_handoff_map(handoff_by_id: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    dst = path or POLICY_HANDOFF_PATH
    write_jsonl(dst, list(handoff_by_id.values()))


def build_handoff_row(
    source: dict[str, Any],
    *,
    easy_read_content: str,
    cardnews_images: list[CardnewsS3Image] | None = None,
) -> dict[str, Any]:
    content_id = row_content_id(source)
    policy_api_id = parse_policy_api_id(source)
    images = cardnews_images or []
    cardnews_urls = [img["url"] for img in images if str(img.get("url") or "").strip()]
    source_url = (source.get("source_url") or "").strip()
    event_start = source.get("event_start_time")
    event_end = source.get("event_end_time")
    title = (source.get("pin_title") or source.get("title") or "").strip()
    return {
        "contentid": content_id,
        "policy_api_id": policy_api_id,
        "title": title,
        "pin_content": (easy_read_content or "").strip(),
        "pin_content_raw": row_raw_content(source),
        "cardnews_image_urls": cardnews_urls,
        "cardnews_images": images,
        "source_url": source_url,
        "event_start_time": event_start,
        "event_end_time": event_end,
        "approve_date": (source.get("approve_date") or "").strip(),
    }


def build_llm_service(*, model: str | None = None) -> IssuePinLLMService:
    secret = settings.gemini_api_key
    if secret is None:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")
    model_name = (model or settings.gemini_pin_text_model).strip()
    fallbacks = parse_gemini_model_list(settings.gemini_pin_text_fallback_models)
    return IssuePinLLMService(
        api_key=secret.get_secret_value(),
        model_name=model_name,
        fallback_models=fallbacks,
    )


async def transform_one_row(
    llm: IssuePinLLMService,
    row: dict[str, Any],
    *,
    s3_util: S3Util,
) -> dict[str, Any]:
    raw_content = row_raw_content(row)
    if not raw_content:
        raise ValueError("pin_content가 비어 있음")

    prompt = build_policy_easy_read_prompt(
        pin_title=str(row.get("pin_title") or ""),
        pin_content=raw_content,
        minister=str(row.get("minister") or ""),
        subtitles=str(row.get("subtitles") or ""),
        approve_date=str(row.get("approve_date") or ""),
    )
    easy_read_text = await llm.generate_pin_text(prompt=prompt)
    cardnews_images = await generate_cardnews_s3_images(
        text_llm=llm,
        row=row,
        easy_read_content=easy_read_text,
        s3_util=s3_util,
    )
    source = {**row, "pin_content_raw": raw_content}
    return build_handoff_row(
        source,
        easy_read_content=easy_read_text,
        cardnews_images=cardnews_images,
    )


def list_pending_transform_rows(
    documents: list[dict[str, Any]],
    handoff_by_id: dict[str, dict[str, Any]],
    *,
    db_policy_api_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    db_ids = db_policy_api_ids or set()
    pending: list[dict[str, Any]] = []
    for row in documents:
        content_id = row_content_id(row)
        if not content_id:
            continue
        policy_id = parse_policy_api_id(row)
        if policy_id is not None and policy_id in db_ids:
            continue
        if content_id in handoff_by_id:
            continue
        pending.append(row)
    return pending


def count_pending_transform(
    documents: list[dict[str, Any]],
    handoff_by_id: dict[str, dict[str, Any]],
    *,
    db_policy_api_ids: set[int] | None = None,
) -> int:
    return len(
        list_pending_transform_rows(
            documents,
            handoff_by_id,
            db_policy_api_ids=db_policy_api_ids,
        ),
    )


async def transform_documents_jsonl(
    *,
    input_path: Path | None = None,
    output_path: Path | None = None,
    limit: int | None = None,
    model: str | None = None,
    s3_util: S3Util | None = None,
    db_policy_api_ids: set[int] | None = None,
    merge_handoff: bool = True,
) -> PolicyPinTransformResult:
    src = input_path or POLICY_DOCUMENTS_PATH
    dst = output_path or POLICY_HANDOFF_PATH
    if not src.is_file():
        raise FileNotFoundError(
            f"원문 JSONL 없음: {src}. 먼저 GET /policy-pins/search 또는 fetch 스크립트를 실행하세요.",
        )

    documents = load_jsonl_rows(src)
    handoff_by_id = load_rows_by_content_id(dst) if merge_handoff else {}
    db_ids = db_policy_api_ids or set()
    pending = list_pending_transform_rows(
        documents,
        handoff_by_id,
        db_policy_api_ids=db_ids,
    )

    llm = build_llm_service(model=model)
    s3 = s3_util or S3Util()
    processed_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped_duplicate_count = 0

    rows_to_process = pending if limit is None else pending[:limit]
    concurrency = min(settings.policy_transform_concurrency, len(rows_to_process) or 1)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _transform_row(row: dict[str, Any]) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
        content_id = row_content_id(row)
        async with semaphore:
            try:
                handoff_row = await transform_one_row(llm, row, s3_util=s3)
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
        policy_id = parse_policy_api_id(row)
        if policy_id is not None and policy_id in db_ids:
            skipped_duplicate_count += 1

    write_handoff_map(handoff_by_id, dst)
    remaining_pending = count_pending_transform(
        documents,
        handoff_by_id,
        db_policy_api_ids=db_ids,
    )
    pins = [PolicyPinHandoffDTO.from_row(item) for item in processed_rows]

    hint: str | None
    if processed_rows or handoff_by_id:
        hint = (
            f"이번 가공 {len(processed_rows)}건, handoff 총 {len(handoff_by_id)}건. "
            "기간 필터는 search(policy_documents.jsonl) 단계에서 적용된 범위입니다."
        )
    else:
        hint = "가공 성공 건이 없습니다. GEMINI_API_KEY·원문 pin_content를 확인하세요."

    return PolicyPinTransformResult(
        input_path=str(src),
        output_path=str(dst),
        processed_count=len(processed_rows),
        error_count=len(errors),
        errors=errors,
        pins=pins,
        hint=hint,
        skipped_duplicate_count=skipped_duplicate_count,
        pending_count=len(pending),
        remaining_pending_count=remaining_pending,
    )
