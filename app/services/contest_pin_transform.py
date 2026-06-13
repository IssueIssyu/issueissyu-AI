from __future__ import annotations

import json
from pathlib import Path

from app.schemas.ContestPinDTO import ContestPinHandoffDTO, ContestPinTransformResult
from app.services.contest_cardnews import generate_contest_cardnews_paths
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.gemini_factory import build_issue_pin_llm_service
from app.utils.pin_content import append_source_link_to_pin_content
from rag.scripts.chunk_module import iter_jsonl, write_jsonl
from rag.scripts.fetch_linkareer_contests import CONTEST_DOCUMENTS_PATH, clean_contest_body

CONTEST_HANDOFF_PATH = (
    Path(__file__).resolve().parents[2] / "rag" / "output" / "contest_pins_for_db.jsonl"
)


def build_handoff_row(
    source: dict,
    *,
    pin_content: str,
    cardnews_image_urls: list[str],
) -> dict:
    source_url = (source.get("source_url") or "").strip()
    body = append_source_link_to_pin_content(pin_content, source_url)
    return {
        "contentid": str(source.get("contentid") or "").strip(),
        "title": (source.get("pin_title") or source.get("title") or "").strip(),
        "pin_content": body,
        "cardnews_image_urls": [str(u).strip() for u in cardnews_image_urls if str(u).strip()],
        "source_url": source_url,
    }


async def transform_one_row(
    llm: IssuePinLLMService,
    row: dict,
    *,
    with_caption: bool = True,
) -> dict:
    pin_title = str(row.get("pin_title") or "").strip()
    raw = clean_contest_body(
        str(row.get("pin_content_raw") or row.get("pin_content") or ""),
        pin_title=pin_title,
    )
    if not raw:
        raise ValueError("pin_content_raw가 비어 있음")

    cardnews_urls, caption = await generate_contest_cardnews_paths(
        llm,
        row={**row, "pin_content_raw": raw},
        with_caption=with_caption,
    )
    if not cardnews_urls:
        raise ValueError("카드뉴스 이미지가 생성되지 않음")

    pin_content = caption if caption else raw
    return build_handoff_row(
        row,
        pin_content=pin_content,
        cardnews_image_urls=cardnews_urls,
    )


async def transform_documents_jsonl(
    *,
    input_path: Path | None = None,
    output_path: Path | None = None,
    limit: int | None = None,
    model: str | None = None,
    with_caption: bool = True,
    contentid: str | None = None,
) -> ContestPinTransformResult:
    src = input_path or CONTEST_DOCUMENTS_PATH
    dst = output_path or CONTEST_HANDOFF_PATH
    if not src.is_file():
        raise FileNotFoundError(
            f"원문 JSONL 없음: {src}. POST /contest-pins/crawl 을 먼저 실행하세요.",
        )

    llm = build_issue_pin_llm_service(model=model)
    results: list[dict] = []
    errors: list[dict] = []
    cid_filter = (contentid or "").strip()

    for row in iter_jsonl(src):
        if not isinstance(row, dict):
            continue
        if cid_filter and str(row.get("contentid") or "").strip() != cid_filter:
            continue
        if limit is not None and len(results) >= limit:
            break

        content_id = str(row.get("contentid") or "").strip()
        try:
            results.append(
                await transform_one_row(llm, row, with_caption=with_caption),
            )
        except Exception as exc:
            errors.append(
                {
                    "contentid": content_id,
                    "pin_title": row.get("pin_title"),
                    "error": str(exc),
                },
            )

    write_jsonl(dst, results)
    pins = [ContestPinHandoffDTO.from_row(item) for item in results]

    hint: str | None
    if results:
        hint = (
            f"response.pins({len(pins)}건)와 {dst.name} 동일. "
            "카드뉴스는 텍스트·캐릭터만 사용(크롤 이미지 미포함)."
        )
    else:
        hint = "가공 성공 건이 없습니다. GEMINI_API_KEY·pin_content_raw를 확인하세요."

    return ContestPinTransformResult(
        input_path=str(src),
        output_path=str(dst),
        processed_count=len(results),
        error_count=len(errors),
        errors=errors,
        pins=pins,
        hint=hint,
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
