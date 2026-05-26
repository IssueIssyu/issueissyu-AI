"""
TourAPI searchFestival2 + 상세 API → festival_documents.jsonl

프로젝트 루트에서: python -m rag.scripts.fetch_visitkorea --start-date 20260101 --end-date 20261231 --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.clients.VisitKoreaClient import VisitKoreaClient
from app.utils.festival_date_filter import validate_yyyymmdd
from app.utils.visitkorea_facilities import (
    extract_stay_available,
    extract_pet_friendly,
)
from rag.scripts.chunk_module import write_jsonl
from rag.scripts.preprocess_module import OUTPUT_DIR, RAW_DIR, clean_text

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = OUTPUT_DIR / "festival_documents.jsonl"
RAW_FESTIVAL_DIR = RAW_DIR / "visitkorea" / "festival"
FESTIVAL_CONTENT_TYPE_ID = "15"


def tourapi_to_latlng(
    *,
    mapx: str | float | None,
    mapy: str | float | None,
) -> dict[str, str | None]:
    def _as_str(value: str | float | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    return {"longitude": _as_str(mapx), "latitude": _as_str(mapy)}


def tourapi_header(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response")
    if isinstance(response, dict):
        return response.get("header") or {}
    return {}


def tourapi_body(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response")
    if isinstance(response, dict):
        return response.get("body") or {}
    return {}


def tourapi_result_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    if "response" in payload:
        header = tourapi_header(payload)
        code = str(header.get("resultCode", ""))
        msg = str(header.get("resultMsg", ""))
    else:
        code = str(payload.get("resultCode", ""))
        msg = str(payload.get("resultMsg", ""))
    return code == "0000", f"{code} {msg}".strip()


def tourapi_body_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = (tourapi_body(payload).get("items") or {}).get("item")
    if items is None:
        return []
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    if isinstance(items, dict):
        return [items]
    return []


def tourapi_total_count(payload: dict[str, Any]) -> int:
    raw = tourapi_body(payload).get("totalCount")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def collect_intro_text(intro_payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in tourapi_body_items(intro_payload):
        name = clean_text(str(item.get("infoname") or ""))
        text = clean_text(str(item.get("infotext") or ""))
        if not text:
            continue
        if name:
            parts.append(f"{name}\n{text}")
        else:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _add_image_url(urls: list[str], seen: set[str], raw: object) -> None:
    url = str(raw or "").strip()
    if not url or url in seen:
        return
    seen.add(url)
    urls.append(url)


def collect_image_urls(
    list_item: dict[str, Any],
    common_item: dict[str, Any] | None,
    image_payload: dict[str, Any] | None,
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for src in (list_item, common_item or {}):
        _add_image_url(urls, seen, src.get("firstimage"))
        _add_image_url(urls, seen, src.get("firstimage2"))
    if image_payload is not None:
        for item in tourapi_body_items(image_payload):
            _add_image_url(urls, seen, item.get("originimgurl"))
            _add_image_url(urls, seen, item.get("smallimageurl"))
    return urls


def merge_pin_content(*, overview: str, intro: str, fallback: str = "") -> str:
    parts: list[str] = []
    ov = clean_text(overview)
    if ov:
        parts.append(ov)
    intro_clean = clean_text(intro)
    if intro_clean and intro_clean not in parts:
        parts.append(intro_clean)
    if not parts and fallback:
        parts.append(clean_text(fallback))
    return "\n\n".join(parts).strip()


def build_document_row(
    *,
    list_item: dict[str, Any],
    common_item: dict[str, Any] | None,
    intro_text: str,
    image_urls: list[str],
    pet_friendly: str,
    stay_available: str,
) -> dict[str, Any] | None:
    content_id = str(list_item.get("contentid") or "").strip()
    if not content_id:
        return None

    merged = {**list_item, **(common_item or {})}
    title = clean_text(str(merged.get("title") or ""))
    if not title:
        return None

    addr = clean_text(str(merged.get("addr1") or ""))
    if merged.get("addr2"):
        addr2 = clean_text(str(merged.get("addr2")))
        addr = f"{addr}, {addr2}" if addr else addr2

    event_start = str(list_item.get("eventstartdate") or merged.get("eventstartdate") or "").strip() or None
    event_end = str(list_item.get("eventenddate") or merged.get("eventenddate") or "").strip() or None

    coords = tourapi_to_latlng(mapx=merged.get("mapx"), mapy=merged.get("mapy"))
    pin_content = merge_pin_content(
        overview=str(merged.get("overview") or ""),
        intro=intro_text,
        fallback=title,
    )

    return {
        "contentid": content_id,
        "pin_title": title,
        "pin_content": pin_content,
        "addr": addr,
        "longitude": coords["longitude"],
        "latitude": coords["latitude"],
        "event_start_time": event_start,
        "event_end_time": event_end,
        "image_urls": image_urls,
        "tel": clean_text(str(merged.get("tel") or "")),
        "pet_friendly": pet_friendly,
        "stay_available": stay_available,
    }


@dataclass(slots=True)
class _FestivalItemDetails:
    common_item: dict[str, Any] | None
    intro_text: str
    intro_payload: dict[str, Any] | None
    pet_tour_payload: dict[str, Any] | None
    image_payload: dict[str, Any] | None
    detail_errors: int


async def _fetch_detail_common(
    client: VisitKoreaClient,
    content_id: str,
) -> tuple[dict[str, Any] | None, bool]:
    try:
        common_payload = await client.detail_common(content_id=content_id)
        ok, msg = tourapi_result_ok(common_payload)
        if ok:
            common_rows = tourapi_body_items(common_payload)
            return (common_rows[0] if common_rows else None), False
        logger.warning("detailCommon2 %s: %s", content_id, msg)
        return None, True
    except Exception:
        logger.exception("detailCommon2 실패 contentid=%s", content_id)
        return None, True


async def _fetch_detail_intro(
    client: VisitKoreaClient,
    content_id: str,
    content_type_id: str,
) -> tuple[str, dict[str, Any] | None, bool]:
    try:
        intro_payload = await client.detail_intro(
            content_id=content_id,
            content_type_id=content_type_id,
        )
        ok, msg = tourapi_result_ok(intro_payload)
        if ok:
            return collect_intro_text(intro_payload), intro_payload, False
        logger.warning("detailIntro2 %s: %s", content_id, msg)
        return "", None, True
    except Exception:
        logger.exception("detailIntro2 실패 contentid=%s", content_id)
        return "", None, True


async def _fetch_detail_pet_tour(
    client: VisitKoreaClient,
    content_id: str,
) -> dict[str, Any] | None:
    try:
        pet_tour_payload = await client.detail_pet_tour(content_id=content_id)
        ok, msg = tourapi_result_ok(pet_tour_payload)
        if ok:
            return pet_tour_payload
        logger.debug("detailPetTour2 %s: %s", content_id, msg)
        return None
    except Exception:
        logger.debug("detailPetTour2 실패 contentid=%s", content_id, exc_info=True)
        return None


async def _fetch_detail_image(
    client: VisitKoreaClient,
    content_id: str,
    *,
    fetch_images: bool,
) -> tuple[dict[str, Any] | None, bool]:
    if not fetch_images:
        return None, False
    try:
        image_payload = await client.detail_image(content_id=content_id)
        ok, msg = tourapi_result_ok(image_payload)
        if ok:
            return image_payload, False
        logger.warning("detailImage2 %s: %s", content_id, msg)
        return None, True
    except Exception:
        logger.exception("detailImage2 실패 contentid=%s", content_id)
        return None, True


async def _fetch_festival_item_details(
    client: VisitKoreaClient,
    *,
    content_id: str,
    content_type_id: str,
    fetch_images: bool,
) -> _FestivalItemDetails:
    (
        (common_item, common_err),
        (intro_text, intro_payload, intro_err),
        pet_tour_payload,
        (image_payload, image_err),
    ) = await asyncio.gather(
        _fetch_detail_common(client, content_id),
        _fetch_detail_intro(client, content_id, content_type_id),
        _fetch_detail_pet_tour(client, content_id),
        _fetch_detail_image(client, content_id, fetch_images=fetch_images),
    )
    return _FestivalItemDetails(
        common_item=common_item,
        intro_text=intro_text,
        intro_payload=intro_payload,
        pet_tour_payload=pet_tour_payload,
        image_payload=image_payload,
        detail_errors=int(common_err) + int(intro_err) + int(image_err),
    )


async def fetch_festival_documents(
    *,
    client: VisitKoreaClient,
    start_date: str,
    end_date: str,
    num_of_rows: int,
    max_pages: int | None,
    limit: int | None,
    skip_detail: bool,
    fetch_images: bool,
    save_raw_pages: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "list_items": 0,
        "documents": 0,
        "skipped_duplicate": 0,
        "skipped_invalid": 0,
        "detail_errors": 0,
        "pages": 0,
    }
    seen_ids: set[str] = set()
    documents: list[dict[str, Any]] = []

    page_no = 1
    total_count: int | None = None

    while True:
        if max_pages is not None and page_no > max_pages:
            break

        list_payload = await client.search_festival(
            event_start_date=start_date,
            event_end_date=end_date,
            page_no=page_no,
            num_of_rows=num_of_rows,
        )
        ok, msg = tourapi_result_ok(list_payload)
        if not ok:
            logger.error("searchFestival2 실패 page=%s: %s", page_no, msg)
            break

        if save_raw_pages:
            RAW_FESTIVAL_DIR.mkdir(parents=True, exist_ok=True)
            raw_path = RAW_FESTIVAL_DIR / f"searchFestival_page_{page_no}.json"
            raw_path.write_text(
                json.dumps(list_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if total_count is None:
            total_count = tourapi_total_count(list_payload)
            logger.info("searchFestival2 totalCount=%s", total_count)

        items = tourapi_body_items(list_payload)
        stats["pages"] += 1
        if not items:
            break

        for list_item in items:
            if limit is not None and stats["documents"] >= limit:
                return documents, stats

            content_id = str(list_item.get("contentid") or "").strip()
            if not content_id:
                stats["skipped_invalid"] += 1
                continue
            if content_id in seen_ids:
                stats["skipped_duplicate"] += 1
                continue
            seen_ids.add(content_id)
            stats["list_items"] += 1

            common_item: dict[str, Any] | None = None
            intro_text = ""
            intro_payload: dict[str, Any] | None = None
            pet_tour_payload: dict[str, Any] | None = None
            image_payload: dict[str, Any] | None = None

            if not skip_detail:
                content_type_id = str(
                    list_item.get("contenttypeid") or FESTIVAL_CONTENT_TYPE_ID
                ).strip()
                details = await _fetch_festival_item_details(
                    client,
                    content_id=content_id,
                    content_type_id=content_type_id,
                    fetch_images=fetch_images,
                )
                common_item = details.common_item
                intro_text = details.intro_text
                intro_payload = details.intro_payload
                pet_tour_payload = details.pet_tour_payload
                image_payload = details.image_payload
                stats["detail_errors"] += details.detail_errors

            image_urls = collect_image_urls(list_item, common_item, image_payload)
            pet_friendly = extract_pet_friendly(
                pet_tour_payload=pet_tour_payload,
                intro_payload=intro_payload,
            )
            stay_available = extract_stay_available(intro_payload=intro_payload)
            row = build_document_row(
                list_item=list_item,
                common_item=common_item,
                intro_text=intro_text,
                image_urls=image_urls,
                pet_friendly=pet_friendly,
                stay_available=stay_available,
            )
            if row is None:
                stats["skipped_invalid"] += 1
                continue

            documents.append(row)
            stats["documents"] += 1
            logger.info(
                "수집 [%d] %s (%s)",
                stats["documents"],
                row["pin_title"][:40],
                content_id,
            )

        if total_count is not None and page_no * num_of_rows >= total_count:
            break
        if len(items) < num_of_rows:
            break
        page_no += 1

    return documents, stats


async def run(args: argparse.Namespace) -> None:
    start_date = validate_yyyymmdd(args.start_date, label="--start-date")
    end_date = validate_yyyymmdd(args.end_date, label="--end-date")

    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with VisitKoreaClient.from_settings() as client:
        documents, stats = await fetch_festival_documents(
            client=client,
            start_date=start_date,
            end_date=end_date,
            num_of_rows=args.num_of_rows,
            max_pages=args.max_pages,
            limit=args.limit,
            skip_detail=args.skip_detail,
            fetch_images=not args.skip_images,
            save_raw_pages=args.save_raw_pages,
        )

    write_jsonl(output_path, documents)

    preview_path = output_path.with_name("festival_documents_preview.json")
    preview = documents[: min(3, len(documents))]
    preview_path.write_text(
        json.dumps(preview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start_date,
        "end_date": end_date,
        "output": str(output_path),
        "stats": stats,
    }
    report_path = output_path.with_name("festival_fetch_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"완료: {output_path}")
    print(f"문서 수: {stats['documents']} (목록 {stats['list_items']}건, 페이지 {stats['pages']})")
    print(f"미리보기: {preview_path}")
    print(f"리포트: {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TourAPI 축제 데이터 → festival_documents.jsonl")
    parser.add_argument(
        "--start-date",
        required=True,
        help="행사 시작일 검색 기준 YYYYMMDD (searchFestival2 eventStartDate)",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="행사 종료일 검색 기준 YYYYMMDD (searchFestival2 eventEndDate)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"출력 JSONL (기본: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--num-of-rows", type=int, default=100, help="페이지당 목록 수 (max 100)")
    parser.add_argument("--max-pages", type=int, default=None, help="최대 페이지 수 (미지정 시 전체)")
    parser.add_argument("--limit", type=int, default=None, help="수집할 축제 최대 건수 (테스트용)")
    parser.add_argument(
        "--skip-detail",
        action="store_true",
        help="detailCommon/Intro/Image 생략 (목록 필드만)",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="detailImage2 호출 생략 (firstimage만)",
    )
    parser.add_argument(
        "--save-raw-pages",
        action="store_true",
        help="목록 API 원본 JSON을 rag/raw/visitkorea/festival/ 에 저장",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG 로그")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    if args.num_of_rows < 1 or args.num_of_rows > 100:
        raise SystemExit("--num-of-rows는 1~100")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
