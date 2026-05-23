from __future__ import annotations

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
    raw_content = (row.get("pin_content") or row.get("text") or "").strip()
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

    llm = build_llm_service(model=model)
    results: list[dict] = []
    errors: list[dict] = []

    for row in iter_jsonl(src):
        if not isinstance(row, dict):
            continue
        if limit is not None and len(results) >= limit:
            break

        content_id = str(row.get("contentid") or "").strip()
        try:
            results.append(await transform_one_row(llm, row))
        except Exception as exc:
            errors.append(
                {
                    "contentid": content_id,
                    "pin_title": row.get("pin_title"),
                    "error": str(exc),
                }
            )

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
