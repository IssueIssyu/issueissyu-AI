from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.utils.visitkorea_area import infer_area_code_from_addr, resolve_row_area_code, row_matches_area_filter
from app.schemas.FestivalPinDTO import FestivalPinDTO, FestivalPinTransformResult
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.gemini_factory import build_issue_pin_llm_service
from app.services.prompts.festival_pin import build_festival_instagram_prompt
from rag.scripts.chunk_module import iter_jsonl, write_jsonl

FESTIVAL_DOCUMENTS_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "festival_documents.jsonl"
)
FESTIVAL_HANDOFF_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "festival_pins_for_db.jsonl"
)
FESTIVAL_PIPELINE_META_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "festival_pipeline_meta.json"
)
FESTIVAL_OUTPUT_DIR = FESTIVAL_DOCUMENTS_PATH.parent

# fetch/transform/import 중복 판단·진행 상태에 쓰이는 로컬 캐시
FESTIVAL_DEDUP_CACHE_FILES: tuple[Path, ...] = (
    FESTIVAL_DOCUMENTS_PATH,
    FESTIVAL_HANDOFF_PATH,
    FESTIVAL_PIPELINE_META_PATH,
    FESTIVAL_OUTPUT_DIR / "festival_import_batch_report.json",
    FESTIVAL_OUTPUT_DIR / "festival_pipeline_report.json",
    FESTIVAL_OUTPUT_DIR / "festival_fetch_report.json",
    FESTIVAL_OUTPUT_DIR / "festival_transform_report.json",
    FESTIVAL_OUTPUT_DIR / "festival_documents_preview.json",
    FESTIVAL_OUTPUT_DIR / "festival_pins_preview.json",
)

FESTIVAL_IMAGE_S3_KEY = "festival"


def reset_festival_dedup_cache() -> list[str]:
    """중복 스킵·핸드오프·메타 등 로컬 JSON 캐시 삭제. DB event_pin은 건드리지 않음."""
    deleted: list[str] = []
    for path in FESTIVAL_DEDUP_CACHE_FILES:
        if path.is_file():
            path.unlink()
            deleted.append(str(path))
    return deleted


def parse_festival_api_id(row: dict[str, Any]) -> int | None:
    raw = row.get("festival_api_id") or row.get("contentid")
    if raw is None:
        return None
    text = str(raw).strip()
    if not text.isdigit():
        return None
    return int(text)


def row_content_id(row: dict[str, Any]) -> str:
    return str(row.get("contentid") or row.get("festival_api_id") or "").strip()


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


def needs_llm_transform(source_row: dict[str, Any], handoff_row: dict[str, Any] | None) -> bool:
    if handoff_row is None:
        return True
    raw_content = row_raw_content(source_row)
    if not raw_content:
        return False
    source_norm = normalize_raw_for_compare(raw_content)
    existing_raw = str(handoff_row.get("pin_content_raw") or "").strip()
    existing_norm = normalize_raw_for_compare(existing_raw)
    existing_generated = str(handoff_row.get("pin_content") or "").strip()
    existing_title = str(handoff_row.get("pin_title") or "").strip()
    if existing_norm == source_norm and existing_generated and existing_title:
        return False
    return True


def reuse_transformed_row_if_unchanged(
    *,
    source_row: dict[str, Any],
    existing_row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if existing_row is None:
        return None
    raw_content = row_raw_content(source_row)
    if not raw_content:
        return None
    source_norm = normalize_raw_for_compare(raw_content)
    existing_raw = str(existing_row.get("pin_content_raw") or "").strip()
    existing_norm = normalize_raw_for_compare(existing_raw)
    existing_generated = str(existing_row.get("pin_content") or "").strip()
    existing_title = str(existing_row.get("pin_title") or "").strip()
    if existing_norm != source_norm or not existing_generated or not existing_title:
        return None
    source_with_raw = {**source_row, "pin_content_raw": raw_content}
    return build_handoff_row(
        source_with_raw,
        pin_title=existing_title,
        pin_content=existing_generated,
    )


def build_handoff_row(
    source: dict[str, Any],
    *,
    pin_title: str,
    pin_content: str,
) -> dict[str, Any]:
    content_id = row_content_id(source)
    raw = (source.get("pin_content_raw") or source.get("pin_content") or "").strip()
    festival_api_id = parse_festival_api_id(source) or (
        int(content_id) if content_id.isdigit() else None
    )
    return {
        "contentid": content_id,
        "festival_api_id": festival_api_id,
        "pin_type": "FESTIVAL",
        "pin_title": (pin_title or source.get("pin_title") or "").strip()[:100],
        "pin_content_raw": raw,
        "pin_content": pin_content.strip(),
        "addr": (source.get("addr") or "").strip(),
        "area_code": source.get("area_code"),
        "sigungu_code": source.get("sigungu_code"),
        "longitude": source.get("longitude"),
        "latitude": source.get("latitude"),
        "event_start_time": source.get("event_start_time"),
        "event_end_time": source.get("event_end_time"),
        "pin_images": list(source.get("pin_images") or []),
        "image_urls": list(source.get("image_urls") or []),
        "tel": (source.get("tel") or "").strip(),
    }


async def transform_one_row(llm: IssuePinLLMService, row: dict[str, Any]) -> dict[str, Any]:
    raw_content = row_raw_content(row)
    if not raw_content:
        raise ValueError("pin_content가 비어 있음")

    prompt = build_festival_instagram_prompt(
        pin_title=str(row.get("pin_title") or ""),
        pin_content=raw_content,
        addr=str(row.get("addr") or ""),
        event_start_time=row.get("event_start_time"),
        event_end_time=row.get("event_end_time"),
        pet_friendly=str(row.get("pet_friendly") or "정보 없음"),
        stay_available=str(row.get("stay_available") or "정보 없음"),
    )
    instagram_text = await llm.generate_pin_text(prompt=prompt)
    source = {**row, "pin_content_raw": raw_content}
    return build_handoff_row(
        source,
        pin_title=str(row.get("pin_title") or ""),
        pin_content=instagram_text,
    )


def count_pending_transform(
    documents: list[dict[str, Any]],
    handoff_by_id: dict[str, dict[str, Any]],
    *,
    area_code: str | None = None,
    sigungu_code: str | None = None,
) -> int:
    return len(
        list_pending_transform_rows(
            documents,
            handoff_by_id,
            area_code=area_code,
            sigungu_code=sigungu_code,
        ),
    )


def list_pending_transform_rows(
    documents: list[dict[str, Any]],
    handoff_by_id: dict[str, dict[str, Any]],
    *,
    area_code: str | None = None,
    sigungu_code: str | None = None,
) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for row in documents:
        if not row_matches_area_filter(row, area_code=area_code, sigungu_code=sigungu_code):
            continue
        content_id = row_content_id(row)
        if not content_id:
            continue
        existing = handoff_by_id.get(content_id)
        if reuse_transformed_row_if_unchanged(source_row=row, existing_row=existing) is not None:
            continue
        if needs_llm_transform(row, existing):
            pending.append(row)
    return pending


def merge_documents(existing: dict[str, dict[str, Any]], new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = dict(existing)
    for row in new_rows:
        content_id = row_content_id(row)
        if content_id:
            merged[content_id] = row
    return list(merged.values())


def write_handoff_map(handoff_by_id: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    dst = path or FESTIVAL_HANDOFF_PATH
    write_jsonl(dst, list(handoff_by_id.values()))


async def transform_documents_batch(
    *,
    batch_size: int | None = None,
    page: int = 1,
    page_size: int = 25,
    area_code: str | None = None,
    sigungu_code: str | None = None,
    input_path: Path | None = None,
    output_path: Path | None = None,
    model: str | None = None,
    enforce_admin_batch_limits: bool = True,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int, dict[str, int]]:
    """pending 목록을 page/page_size로 나눠 LLM 가공. Admin API는 batch_size 5 또는 25."""
    if page < 1:
        raise ValueError("page는 1 이상이어야 합니다.")
    if enforce_admin_batch_limits:
        effective_page_size = page_size if page_size in (5, 25) else 25
        effective_batch = batch_size if batch_size is not None else effective_page_size
        if effective_batch not in (5, 25):
            raise ValueError("batch_size는 5 또는 25만 허용됩니다.")
    else:
        effective_page_size = max(1, page_size)
        effective_batch = batch_size if batch_size is not None else effective_page_size
        if effective_batch < 1:
            raise ValueError("batch_size는 1 이상이어야 합니다.")

    src = input_path or FESTIVAL_DOCUMENTS_PATH
    dst = output_path or FESTIVAL_HANDOFF_PATH
    if not src.is_file():
        raise FileNotFoundError(
            f"원문 JSONL 없음: {src}. 먼저 POST /festival-admin/fetch-year (또는 /fetch)를 실행하세요.",
        )

    documents = load_jsonl_rows(src)
    if not documents:
        raise FileNotFoundError(
            f"원문 JSONL이 비어 있습니다: {src}. fetch-year가 완료될 때까지 기다리거나 다시 실행하세요.",
        )
    handoff_by_id = load_rows_by_content_id(dst)

    pending_all = list_pending_transform_rows(
        documents,
        handoff_by_id,
        area_code=area_code,
        sigungu_code=sigungu_code,
    )
    total_pending = len(pending_all)
    total_pages = max(1, (total_pending + effective_page_size - 1) // effective_page_size) if total_pending else 0

    start_idx = (page - 1) * effective_page_size
    page_rows = pending_all[start_idx : start_idx + effective_page_size]

    processed_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped_duplicate_count = 0
    llm_pending: list[dict[str, Any]] = []

    for row in page_rows:
        content_id = row_content_id(row)
        if not content_id:
            continue
        existing = handoff_by_id.get(content_id)
        reused = reuse_transformed_row_if_unchanged(source_row=row, existing_row=existing)
        if reused is not None:
            handoff_by_id[content_id] = reused
            skipped_duplicate_count += 1
            continue
        if not needs_llm_transform(row, existing):
            skipped_duplicate_count += 1
            continue
        llm_pending.append(row)

    llm_rows = llm_pending[:effective_batch]

    if llm_rows:
        llm = build_issue_pin_llm_service(model=model)
        concurrency = min(settings.festival_transform_concurrency, len(llm_rows))
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _transform_row(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
            content_id = row_content_id(row)
            async with semaphore:
                try:
                    return await transform_one_row(llm, row), None
                except Exception as exc:
                    return None, {
                        "contentid": content_id,
                        "festival_api_id": parse_festival_api_id(row),
                        "pin_title": row.get("pin_title"),
                        "error": str(exc),
                    }

        for ok_row, err_row in await asyncio.gather(*(_transform_row(row) for row in llm_rows)):
            if ok_row is not None:
                content_id = row_content_id(ok_row)
                handoff_by_id[content_id] = ok_row
                processed_rows.append(ok_row)
            elif err_row is not None:
                errors.append(err_row)

    write_handoff_map(handoff_by_id, dst)
    page_meta = {
        "page": page,
        "page_size": effective_page_size,
        "total_pages": total_pages,
        "total_pending_before_page": total_pending,
        "requested_batch_size": effective_batch,
    }
    return handoff_by_id, processed_rows, errors, skipped_duplicate_count, page_meta


async def transform_documents_jsonl(
    *,
    input_path: Path | None = None,
    output_path: Path | None = None,
    limit: int | None = None,
    model: str | None = None,
) -> FestivalPinTransformResult:
    effective_limit = limit if limit is not None else 10_000
    handoff_by_id, processed_rows, errors, skipped, _page_meta = await transform_documents_batch(
        batch_size=effective_limit,
        page=1,
        page_size=effective_limit,
        input_path=input_path,
        output_path=output_path,
        model=model,
        enforce_admin_batch_limits=False,
    )
    src = input_path or FESTIVAL_DOCUMENTS_PATH
    dst = output_path or FESTIVAL_HANDOFF_PATH
    pins = [FestivalPinDTO.model_validate(item) for item in processed_rows]

    return FestivalPinTransformResult(
        input_path=str(src),
        output_path=str(dst),
        processed_count=len(processed_rows),
        error_count=len(errors),
        errors=errors,
        pins=pins,
        hint=None
        if processed_rows
        else "가공 성공 건이 없습니다. GEMINI_API_KEY·원문 pin_content를 확인하세요.",
    )
