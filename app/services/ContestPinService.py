from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.ContestPinDTO import (
    ContestCrawlResult,
    ContestDocumentDTO,
    ContestDocumentsListResult,
    ContestPinHandoffResult,
    ContestPinTransformResult,
)
from app.services.contest_pin_transform import (
    CONTEST_HANDOFF_PATH,
    load_handoff_from_jsonl,
    transform_documents_jsonl,
)
from app.utils.festival_date_filter import festival_overlaps_range
from rag.scripts.fetch_linkareer_contests import (
    CONTEST_DOCUMENTS_PATH,
    normalize_contest_row,
    run_crawl,
)

_MAX_LIST_ITEMS = 500


def _ensure_playwright_ready() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "playwright 패키지가 없습니다. "
            "서버 venv에서: pip install playwright && python -m playwright install chromium"
        ) from exc

def _run_crawl_in_proactor_thread(
    *,
    max_pages: int,
    limit: int | None,
    delay: float,
    force: bool,
) -> dict[str, Any]:
    """
    uvicorn(Windows)은 SelectorEventLoop를 쓰는 경우가 많아 Playwright subprocess가
    NotImplementedError를 낸다. 별도 스레드에서 Proactor 루프로 크롤을 실행한다.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            run_crawl(
                max_pages=max_pages,
                limit=limit,
                delay=delay,
                force=force,
            )
        )
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


class ContestPinService:
    @staticmethod
    def documents_path() -> Path:
        return CONTEST_DOCUMENTS_PATH

    @staticmethod
    def handoff_path() -> Path:
        return CONTEST_HANDOFF_PATH

    async def crawl_and_save(
        self,
        *,
        max_pages: int = 5,
        limit: int | None = None,
        delay: float = 1.0,
        force: bool = False,
    ) -> ContestCrawlResult:
        _ensure_playwright_ready()
        if sys.platform == "win32":
            stats = await asyncio.to_thread(
                _run_crawl_in_proactor_thread,
                max_pages=max_pages,
                limit=limit,
                delay=delay,
                force=force,
            )
        else:
            stats = await run_crawl(
                max_pages=max_pages,
                limit=limit,
                delay=delay,
                force=force,
            )
        hint = (
            f"{stats['new_count']}건 신규 저장. "
            f"다음: GET /contest-pins/documents"
        )
        if stats["errors"]:
            hint = f"일부 오류 발생({stats['errors']}건). " + hint
        return ContestCrawlResult(
            saved_documents_path=stats["saved_documents_path"],
            new_count=stats["new_count"],
            skipped_expired=stats["skipped_expired"],
            skipped_duplicate=stats["skipped_duplicate"],
            errors=stats["errors"],
            total_count=stats["total_count"],
            hint=hint,
        )

    def load_documents_from_jsonl(
        self,
        *,
        file_path: Path | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        contentid: str | None = None,
    ) -> ContestDocumentsListResult:
        path = file_path or self.documents_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"원문 JSONL 없음: {path}. "
                "POST /contest-pins/crawl 또는 fetch_linkareer_contests 스크립트를 먼저 실행하세요.",
            )

        effective_limit = _MAX_LIST_ITEMS if limit is None else min(limit, _MAX_LIST_ITEMS)
        use_date_filter = start_date is not None and end_date is not None
        cid_filter = (contentid or "").strip()

        matched: list[ContestDocumentDTO] = []
        total_in_file = 0

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total_in_file += 1
                row = normalize_contest_row(json.loads(line))
                try:
                    item = ContestDocumentDTO.model_validate(row)
                except ValidationError as exc:
                    raise ValueError(
                        f"JSONL 형식 오류 (line {total_in_file}, contentid={row.get('contentid')}): {exc}"
                    ) from exc

                if cid_filter and item.contentid != cid_filter:
                    continue

                if use_date_filter and not festival_overlaps_range(
                    event_start=item.event_start_time,
                    event_end=item.event_end_time,
                    query_start=start_date,
                    query_end=end_date,
                ):
                    continue

                matched.append(item)

        documents = matched[:effective_limit]

        hint: str | None = None
        if total_in_file == 0:
            hint = "JSONL이 비어 있습니다. POST /contest-pins/crawl 을 실행하세요."
        elif len(documents) == 0:
            if cid_filter:
                hint = f"contentid={cid_filter} 에 해당하는 공모전이 없습니다."
            elif use_date_filter:
                hint = "기간 필터에 맞는 공모전이 없습니다. start_date/end_date를 비우세요."
            else:
                hint = "조회 결과가 없습니다."

        return ContestDocumentsListResult(
            filter_start_date=start_date,
            filter_end_date=end_date,
            saved_documents_path=str(path),
            total_in_file=total_in_file,
            matched_count=len(matched),
            count=len(documents),
            documents=documents,
            hint=hint,
        )

    async def cardnews_and_save(
        self,
        *,
        limit: int | None = None,
        model: str | None = None,
        with_caption: bool = True,
        contentid: str | None = None,
    ) -> ContestPinTransformResult:
        return await transform_documents_jsonl(
            limit=limit,
            model=model,
            with_caption=with_caption,
            contentid=contentid,
        )

    def load_handoff_from_jsonl(
        self,
        *,
        limit: int | None = None,
    ) -> ContestPinHandoffResult:
        path, pins, total_in_file = load_handoff_from_jsonl(limit=limit)
        hint: str | None = None
        if total_in_file == 0:
            hint = "JSONL이 비어 있습니다. POST /contest-pins/cardnews 를 먼저 실행하세요."
        return ContestPinHandoffResult(
            output_path=str(path),
            total_in_file=total_in_file,
            count=len(pins),
            pins=pins,
            hint=hint,
        )
