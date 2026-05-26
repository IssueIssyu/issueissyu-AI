from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.schemas.PolicyPinDTO import PolicyPinHandoffDTO, PolicyPinTransformResult
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.gemini_retry import parse_gemini_model_list
from app.services.policy_cardnews import generate_cardnews_image_paths
from app.services.prompts.policy_pin import build_policy_easy_read_prompt
from rag.scripts.chunk_module import iter_jsonl, write_jsonl

POLICY_DOCUMENTS_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "policy_documents.jsonl"
)
POLICY_HANDOFF_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "policy_pins_for_db.jsonl"
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


def build_handoff_row(
    source: dict,
    *,
    easy_read_content: str,
    cardnews_image_urls: list[str] | None = None,
) -> dict:
    # DB 전달 JSONL 1행: title, pin_content, cardnews_image_urls, source_url 만
    cardnews_urls = [
        str(url).strip()
        for url in (
            cardnews_image_urls
            if cardnews_image_urls is not None
            else (source.get("cardnews_image_urls") or [])
        )
        if str(url).strip()
    ]
    source_url = (source.get("source_url") or "").strip()
    return {
        "title": (source.get("pin_title") or source.get("title") or "").strip(),
        "pin_content": append_source_link_to_pin_content(easy_read_content, source_url),
        "cardnews_image_urls": cardnews_urls,
        "source_url": source_url,
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

    prompt = build_policy_easy_read_prompt(
        pin_title=str(row.get("pin_title") or ""),
        pin_content=raw_content,
        minister=str(row.get("minister") or ""),
        subtitles=str(row.get("subtitles") or ""),
        approve_date=str(row.get("approve_date") or ""),
    )
    easy_read_text = await llm.generate_pin_text(prompt=prompt)
    cardnews_urls = await generate_cardnews_image_paths(
        llm,
        row=row,
        easy_read_content=easy_read_text,
    )
    raw_html = (row.get("pin_content_raw") or raw_content).strip()
    source = {**row, "pin_content_raw": raw_html}
    return build_handoff_row(
        source,
        easy_read_content=easy_read_text,
        cardnews_image_urls=cardnews_urls,
    )


async def transform_documents_jsonl(
    *,
    input_path: Path | None = None,
    output_path: Path | None = None,
    limit: int | None = None,
    model: str | None = None,
) -> PolicyPinTransformResult:
    src = input_path or POLICY_DOCUMENTS_PATH
    dst = output_path or POLICY_HANDOFF_PATH
    if not src.is_file():
        raise FileNotFoundError(
            f"원문 JSONL 없음: {src}. 먼저 GET /policy-pins/search 또는 fetch 스크립트를 실행하세요.",
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
    pins = [PolicyPinHandoffDTO.from_row(item) for item in results]

    hint: str | None
    if results:
        hint = (
            f"response.pins({len(pins)}건)와 {dst.name} 내용이 동일합니다. "
            "기간 필터는 이미 search(policy_documents.jsonl) 단계에서 적용된 범위입니다."
        )
    else:
        hint = "가공 성공 건이 없습니다. GEMINI_API_KEY·원문 pin_content를 확인하세요."

    return PolicyPinTransformResult(
        input_path=str(src),
        output_path=str(dst),
        processed_count=len(results),
        error_count=len(errors),
        errors=errors,
        pins=pins,
        hint=hint,
    )
