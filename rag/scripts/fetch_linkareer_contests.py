"""
Linkareer 공모전 목록/상세 크롤링 → contest_documents.jsonl

참고:
  - https://dev-studyingblog.tistory.com/104 (목록·상세 수집, robots.txt, Selenium)
  - https://github.com/software-gathering/gather-be2/blob/main/crawling/crawler.py
    (상세 진입, organization-name, YYYY.MM.DD 날짜, card-image)
  - https://sanseo.tistory.com/entry/공모전-크롤링-4-데이터-수집-스크래핑-링커리어
    (list/contest?page= 페이지네이션)

실행 (프로젝트 루트):
  python -m rag.scripts.fetch_linkareer_contests
  python -m rag.scripts.fetch_linkareer_contests --max-pages 2 --limit 5 -v

사전 준비:
  pip install playwright
  python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rag.scripts.chunk_module import iter_jsonl, write_jsonl
from rag.scripts.preprocess_module import OUTPUT_DIR, clean_text, normalize_unicode_whitespace

from app.utils.contest_images import collect_contest_pin_image_specs

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = OUTPUT_DIR / "contest_documents.jsonl"
LIST_URL = "https://linkareer.com/list/contest"
ACTIVITY_ID_RE = re.compile(r"/activity/(\d+)")
DATE_DOT_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
DATE_START_RE = re.compile(r"시작일\s*(\d{4}\.\d{2}\.\d{2})")
DATE_END_RE = re.compile(r"마감일\s*(\d{4}\.\d{2}\.\d{2})")
# 본문 접수기간 등 (시작일/마감일 라벨이 없을 때 fallback)
DATE_IN_TEXT_RE = re.compile(
    r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]?\s*(\d{1,2})",
)
UI_NOISE_LINE_RE = re.compile(
    r"^(\+\d+|상세내용|더보기|공유하기|스크랩|좋아요|댓글\s*\d*)$",
    re.IGNORECASE,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

JS_LIST_ACTIVITY_IDS = """() => [...new Set(
  Array.from(document.querySelectorAll('a[href*="/activity/"]'))
    .map(a => (a.href || '').match(/\\/activity\\/(\\d+)/))
    .filter(Boolean)
    .map(m => m[1])
)]"""

JS_DETAIL = """() => {
  const info =
    document.querySelector('[class*="ActivityInfo-desktop"]') ||
    document.querySelector('.activity-info') ||
    document.querySelector('[class*="ActivityInfo"]');
  const infoText = info ? info.innerText : '';
  const startMatch = infoText.match(/시작일\\s*(\\d{4}\\.\\d{2}\\.\\d{2})/);
  const endMatch = infoText.match(/마감일\\s*(\\d{4}\\.\\d{2}\\.\\d{2})/);
  const tab = document.querySelector('[class*="ActivityDetailTabContent"]');
  let body = tab ? tab.innerText : '';
  if (body.startsWith('상세내용')) body = body.replace(/^상세내용\\s*/,'').trim();

  const orgEl = document.querySelector('.organization-name');
  const host = orgEl ? orgEl.innerText.trim() : '';

  const imgs = new Set();
  const og = document.querySelector('meta[property="og:image"]')?.content;
  if (og && og.startsWith('http')) imgs.add(og);
  const poster = document.querySelector('[class*="card-image"] img');
  if (poster?.src && poster.src.startsWith('http') && !poster.src.includes('data:image')) {
    imgs.add(poster.src);
  }
  if (tab) {
    for (const img of tab.querySelectorAll('img')) {
      const src = img.currentSrc || img.src;
      if (src && src.startsWith('http') && !src.includes('data:image')) imgs.add(src);
    }
  }

  return {
    title: (document.querySelector('h1')?.innerText || '').trim(),
    infoText,
    startDot: startMatch ? startMatch[1] : null,
    endDot: endMatch ? endMatch[1] : null,
    body,
    host,
    images: [...imgs].filter(u => !u.includes('/static/images/new_main/icon/')),
  };
}"""


def parse_contentid(url: str) -> str | None:
    match = ACTIVITY_ID_RE.search(url)
    return match.group(1) if match else None


def dot_date_to_yyyymmdd(value: str | None) -> str | None:
    if not value:
        return None
    match = DATE_DOT_RE.search(value.strip())
    if not match:
        return None
    y, m, d = match.groups()
    return f"{y}{m}{d}"


def _dates_from_text_blob(text: str) -> tuple[str | None, str | None]:
    found: list[str] = []
    for y, m, d in DATE_IN_TEXT_RE.findall(text):
        found.append(f"{y}{int(m):02d}{int(d):02d}")
    if not found:
        return None, None
    if len(found) == 1:
        return found[0], found[0]
    return found[0], found[-1]


def clean_contest_body(text: str, *, pin_title: str = "") -> str:
    """Linkareer UI 잡음(+3, NBSP/ZWSP 등) 제거."""
    if not text:
        return ""
    text = normalize_unicode_whitespace(text)
    lines: list[str] = []
    title_norm = pin_title.strip()
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if UI_NOISE_LINE_RE.match(stripped):
            continue
        if title_norm and stripped == title_norm and not lines:
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def parse_period_from_info(info_text: str) -> tuple[str | None, str | None]:
    start_match = DATE_START_RE.search(info_text)
    end_match = DATE_END_RE.search(info_text)
    start = dot_date_to_yyyymmdd(start_match.group(1)) if start_match else None
    end = dot_date_to_yyyymmdd(end_match.group(1)) if end_match else None
    if start or end:
        return start, end
    found = DATE_DOT_RE.findall(info_text.replace(" ", ""))
    if not found:
        return None, None
    pairs = [f"{y}{m}{d}" for y, m, d in found]
    if len(pairs) == 1:
        return pairs[0], pairs[0]
    return pairs[0], pairs[1]


def resolve_event_period(
    *,
    info_text: str,
    body_text: str,
    start_dot: str | None,
    end_dot: str | None,
) -> tuple[str | None, str | None]:
    if start_dot or end_dot:
        return (
            dot_date_to_yyyymmdd(str(start_dot or "")),
            dot_date_to_yyyymmdd(str(end_dot or "")),
        )
    start, end = parse_period_from_info(info_text)
    if start or end:
        return start, end
    return _dates_from_text_blob(body_text[:4000])


def contest_today_kst() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def is_expired(end_yyyymmdd: str | None, *, today: date) -> bool:
    if not end_yyyymmdd or len(end_yyyymmdd) != 8:
        return False
    try:
        end = datetime.strptime(end_yyyymmdd, "%Y%m%d").date()
    except ValueError:
        return False
    return end < today


def is_contest_row_expired(row: dict[str, Any]) -> bool:
    return is_expired(row.get("event_end_time"), today=contest_today_kst())


def load_existing_documents(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in iter_jsonl(path):
        if not isinstance(row, dict):
            continue
        cid = str(row.get("contentid") or "").strip()
        if cid:
            out[cid] = row
    return out


def normalize_source_url(contentid: str) -> str:
    return f"https://linkareer.com/activity/{contentid}"


def normalize_contest_row(row: dict[str, Any]) -> dict[str, Any]:
    """JSONL 1건 필드 정규화 (기존 파일 재크롤 없이 정리할 때 사용)."""
    title = clean_text(str(row.get("pin_title") or ""))
    raw = clean_contest_body(
        clean_text(str(row.get("pin_content_raw") or "")),
        pin_title=title,
    )
    return {
        **row,
        "pin_title": title,
        "pin_content_raw": raw,
        "host_org": clean_text(str(row.get("host_org") or "")),
    }


def build_document(
    *,
    contentid: str,
    pin_title: str,
    pin_content_raw: str,
    source_url: str,
    image_urls: list[str],
    event_start_time: str | None,
    event_end_time: str | None,
    host_org: str,
    crawled_at: str,
    pin_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    specs = pin_images if pin_images is not None else collect_contest_pin_image_specs(image_urls)
    return {
        "contentid": contentid,
        "pin_title": pin_title,
        "pin_content_raw": pin_content_raw,
        "source_url": source_url,
        "image_urls": image_urls,
        "pin_images": specs,
        "event_start_time": event_start_time,
        "event_end_time": event_end_time,
        "host_org": host_org,
        "crawled_at": crawled_at,
    }


async def collect_list_contentids(page: Any, *, page_num: int) -> list[str]:
    url = f"{LIST_URL}?page={page_num}"
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(2_500)
    ids = await page.evaluate(JS_LIST_ACTIVITY_IDS)
    return [str(i) for i in ids if str(i).isdigit()]


async def scrape_detail(page: Any, contentid: str) -> dict[str, Any] | None:
    source_url = normalize_source_url(contentid)
    await page.goto(source_url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(2_000)

    try:
        await page.wait_for_selector("h1", timeout=15_000)
    except Exception:
        logger.warning("h1 없음: %s", source_url)
        return None

    payload = await page.evaluate(JS_DETAIL)
    pin_title = clean_text(str(payload.get("title") or ""))
    info_text = clean_text(str(payload.get("infoText") or ""))
    pin_content_raw = clean_contest_body(
        clean_text(str(payload.get("body") or "")),
        pin_title=pin_title,
    )
    host_org = clean_text(str(payload.get("host") or ""))

    if not pin_title:
        logger.warning("제목 없음: %s", source_url)
        return None
    if not pin_content_raw:
        pin_content_raw = clean_contest_body(info_text, pin_title=pin_title) or pin_title

    event_start_time, event_end_time = resolve_event_period(
        info_text=info_text,
        body_text=pin_content_raw,
        start_dot=payload.get("startDot"),
        end_dot=payload.get("endDot"),
    )
    image_urls = []
    seen_img: set[str] = set()
    for raw in payload.get("images") or []:
        url = str(raw).strip()
        if not url or url in seen_img:
            continue
        if "linkareer.com/_next/image" in url and "icon" in url:
            continue
        seen_img.add(url)
        image_urls.append(url)

    return build_document(
        contentid=contentid,
        pin_title=pin_title,
        pin_content_raw=pin_content_raw,
        source_url=source_url,
        image_urls=image_urls,
        event_start_time=event_start_time,
        event_end_time=event_end_time,
        host_org=host_org,
        crawled_at=datetime.now().isoformat(timespec="seconds"),
    )


CONTEST_DOCUMENTS_PATH = DEFAULT_OUTPUT


async def run_crawl(
    *,
    output_path: Path | None = None,
    max_pages: int = 5,
    start_page: int = 1,
    limit: int | None = None,
    delay: float = 1.0,
    force: bool = False,
    headed: bool = False,
) -> dict[str, Any]:
    """API·서비스에서 호출하는 크롤 진입점."""
    args = argparse.Namespace(
        output=output_path or DEFAULT_OUTPUT,
        max_pages=max_pages,
        start_page=start_page,
        limit=limit,
        delay=delay,
        headed=headed,
        force=force,
        verbose=False,
    )
    return await _run_impl(args)


async def run(args: argparse.Namespace) -> int:
    stats = await _run_impl(args)
    return 1 if stats.get("errors") else 0


async def _run_impl(args: argparse.Namespace) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    output_path: Path = args.output
    today = contest_today_kst()
    existing_by_id = load_existing_documents(output_path)
    if existing_by_id and not args.force:
        logger.info("기존 JSONL %d건 — 중복 contentid skip", len(existing_by_id))

    queued: list[str] = []
    global_seen: set[str] = set(existing_by_id.keys())

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.headed)
        context = await browser.new_context(user_agent=USER_AGENT, locale="ko-KR")
        page = await context.new_page()

        start_page = max(1, int(getattr(args, "start_page", 1) or 1))
        end_page = start_page + max(0, args.max_pages - 1)
        for page_num in range(start_page, end_page + 1):
            try:
                page_ids = await collect_list_contentids(page, page_num=page_num)
            except Exception as exc:
                logger.error("목록 page=%s 실패: %s", page_num, exc)
                break

            new_on_page = 0
            for cid in page_ids:
                if cid in global_seen:
                    continue
                global_seen.add(cid)
                queued.append(cid)
                new_on_page += 1

            logger.info(
                "목록 page=%s: 카드 %d건, 신규 ID %d건 (누적 대기 %d건)",
                page_num,
                len(page_ids),
                new_on_page,
                len(queued),
            )
            if new_on_page == 0:
                logger.info("신규 ID 없음 — 목록 순회 종료")
                break

            if args.delay > 0:
                await asyncio.sleep(args.delay)

        if args.limit is not None:
            queued = queued[: args.limit]

        new_docs: list[dict[str, Any]] = []
        skipped_expired = 0
        skipped_duplicate = 0
        errors = 0

        for idx, contentid in enumerate(queued, start=1):
            if contentid in existing_by_id and not args.force:
                skipped_duplicate += 1
                continue

            logger.info("[%d/%d] 상세 수집 %s", idx, len(queued), contentid)
            try:
                doc = await scrape_detail(page, contentid)
            except Exception as exc:
                errors += 1
                logger.error("상세 실패 %s: %s", contentid, exc)
                continue

            if doc is None:
                errors += 1
                continue

            if is_expired(doc.get("event_end_time"), today=today):
                skipped_expired += 1
                logger.info(
                    "마감 제외 %s (end=%s)",
                    contentid,
                    doc.get("event_end_time"),
                )
                continue

            new_docs.append(doc)
            existing_by_id[contentid] = doc

            if args.delay > 0:
                await asyncio.sleep(args.delay)

        await browser.close()

    all_rows = [
        normalize_contest_row(existing_by_id[k])
        for k in sorted(existing_by_id.keys())
    ]
    write_jsonl(output_path, all_rows)
    logger.info(
        "저장 완료: %s (이번 신규 %d건, 마감제외 %d, 중복skip %d, 오류 %d, 총 %d건)",
        output_path,
        len(new_docs),
        skipped_expired,
        skipped_duplicate,
        errors,
        len(all_rows),
    )
    return {
        "saved_documents_path": str(output_path),
        "new_count": len(new_docs),
        "skipped_expired": skipped_expired,
        "skipped_duplicate": skipped_duplicate,
        "errors": errors,
        "total_count": len(all_rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Linkareer 공모전 크롤링 → contest_documents.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"출력 JSONL (기본: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="목록 시작 페이지 번호 (기본 1)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="시작 페이지부터 순회할 페이지 수 (신규 ID 없으면 조기 종료)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="상세 수집 최대 건수 (테스트용)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="요청 간 대기(초)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="브라우저 UI 표시",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 JSONL에 있는 contentid도 상세 재수집",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
