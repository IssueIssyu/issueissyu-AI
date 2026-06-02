from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import settings
from app.schemas.FestivalPinDTO import FestivalPinDTO, FestivalPinTransformResult
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.gemini_retry import parse_gemini_model_list
from app.services.prompts.festival_pin import build_festival_instagram_prompt
from rag.scripts.chunk_module import iter_jsonl, write_jsonl

FESTIVAL_DOCUMENTS_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "festival_documents.jsonl"
)
FESTIVAL_HANDOFF_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "festival_pins_for_db.jsonl"
)


def _row_content_id(row: dict) -> str:
    return str(row.get("contentid") or "").strip()


def _row_raw_content(row: dict) -> str:
    return (row.get("pin_content_raw") or row.get("pin_content") or row.get("text") or "").strip()


def _normalize_raw_for_compare(text: str) -> str:
    # 재수집 시 공백/줄바꿈 차이로 불필요 재가공되는 것을 줄인다.
    return " ".join((text or "").split()).strip()


def _load_existing_handoff_by_contentid(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    out: dict[str, dict] = {}
    for row in iter_jsonl(path):
        if not isinstance(row, dict):
            continue
        content_id = _row_content_id(row)
        if not content_id:
            continue
        out[content_id] = row
    return out


def _reuse_transformed_row_if_unchanged(
    *,
    source_row: dict,
    existing_row: dict | None,
) -> dict | None:
    if existing_row is None:
        return None
    raw_content = _row_raw_content(source_row)
    if not raw_content:
        return None
    source_norm = _normalize_raw_for_compare(raw_content)
    existing_raw = str(existing_row.get("pin_content_raw") or "").strip()
    existing_norm = _normalize_raw_for_compare(existing_raw)
    existing_generated = str(existing_row.get("pin_content") or "").strip()
    if existing_norm != source_norm or not existing_generated:
        return None
    source_with_raw = {**source_row, "pin_content_raw": raw_content}
    return build_handoff_row(source_with_raw, instagram_content=existing_generated)


def build_handoff_row(source: dict, *, instagram_content: str) -> dict:
    raw = (source.get("pin_content_raw") or source.get("pin_content") or "").strip()
    return {
        "contentid": str(source.get("contentid") or "").strip(),
        "pin_type": "FESTIVAL",
        "pin_title": (source.get("pin_title") or "").strip(),
        "pin_content_raw": raw,
        "pin_content": instagram_content.strip(),
        "addr": (source.get("addr") or "").strip(),
        "longitude": source.get("longitude"),
        "latitude": source.get("latitude"),
        "event_start_time": source.get("event_start_time"),
        "event_end_time": source.get("event_end_time"),
        "image_urls": list(source.get("image_urls") or []),
        "tel": (source.get("tel") or "").strip(),
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


async def transform_one_row(llm: IssuePinLLMService, row: dict) -> dict:
    raw_content = _row_raw_content(row)
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
    return build_handoff_row(source, instagram_content=instagram_text)


async def transform_documents_jsonl(
    *,
    input_path: Path | None = None,
    output_path: Path | None = None,
    limit: int | None = None,
    model: str | None = None,
) -> FestivalPinTransformResult:
    src = input_path or FESTIVAL_DOCUMENTS_PATH
    dst = output_path or FESTIVAL_HANDOFF_PATH
    if not src.is_file():
        raise FileNotFoundError(
            f"원문 JSONL 없음: {src}. 먼저 GET /festival-pins/search 또는 fetch 스크립트를 실행하세요.",
        )

    rows = [row for row in iter_jsonl(src) if isinstance(row, dict)]
    existing_by_content_id = _load_existing_handoff_by_contentid(dst)

    results: list[dict] = []
    errors: list[dict] = []
    pending_rows: list[dict] = []

    for row in rows:
        if limit is not None and len(results) >= limit:
            break
        reused = _reuse_transformed_row_if_unchanged(
            source_row=row,
            existing_row=existing_by_content_id.get(_row_content_id(row)),
        )
        if reused is not None:
            results.append(reused)
            continue
        pending_rows.append(row)

    if pending_rows:
        llm = build_llm_service(model=model)
        concurrency = settings.festival_transform_concurrency
        semaphore = asyncio.Semaphore(concurrency)

        async def _transform_row(row: dict) -> tuple[dict | None, dict | None]:
            content_id = _row_content_id(row)
            async with semaphore:
                try:
                    return await transform_one_row(llm, row), None
                except Exception as exc:
                    return None, {
                        "contentid": content_id,
                        "pin_title": row.get("pin_title"),
                        "error": str(exc),
                    }

        idx = 0
        while idx < len(pending_rows) and (limit is None or len(results) < limit):
            batch_size = concurrency
            if limit is not None:
                batch_size = min(batch_size, limit - len(results))
            batch_size = min(batch_size, len(pending_rows) - idx)
            batch = pending_rows[idx : idx + batch_size]
            idx += len(batch)
            for ok_row, err_row in await asyncio.gather(*(_transform_row(row) for row in batch)):
                if ok_row is not None:
                    if limit is None or len(results) < limit:
                        results.append(ok_row)
                elif err_row is not None:
                    errors.append(err_row)

    write_jsonl(dst, results)
    pins = [FestivalPinDTO.model_validate(item) for item in results]

    return FestivalPinTransformResult(
        input_path=str(src),
        output_path=str(dst),
        processed_count=len(results),
        error_count=len(errors),
        errors=errors,
        pins=pins,
        hint=None
        if results
        else "가공 성공 건이 없습니다. GEMINI_API_KEY·원문 pin_content를 확인하세요.",
    )
