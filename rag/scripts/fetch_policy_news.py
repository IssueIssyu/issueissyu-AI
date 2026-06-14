"""
정책브리핑 정책뉴스 OpenAPI → policy_documents.jsonl

프로젝트 루트에서:
  python -m rag.scripts.fetch_policy_news --start-date 20260522 --end-date 20260524 --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.clients.PolicyNewsClient import PolicyNewsClient
from app.utils.policy_news_parse import (
    build_policy_document_row,
    is_embargo_active,
    iter_date_chunks,
    validate_yyyymmdd,
)
from rag.scripts.chunk_module import write_jsonl
from rag.scripts.preprocess_module import OUTPUT_DIR

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = OUTPUT_DIR / "policy_documents.jsonl"


async def fetch_policy_documents(
    *,
    client: PolicyNewsClient,
    start_date: str,
    end_date: str,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "chunks": 0,
        "list_items": 0,
        "documents": 0,
        "skipped_duplicate": 0,
        "skipped_invalid": 0,
        "skipped_embargo": 0,
        "api_errors": 0,
    }
    seen_ids: set[str] = set()
    documents: list[dict[str, Any]] = []

    for chunk_start, chunk_end in iter_date_chunks(start_date, end_date):
        if limit is not None and stats["documents"] >= limit:
            break

        stats["chunks"] += 1
        try:
            _header, items = await client.policy_news_list(
                start_date=chunk_start,
                end_date=chunk_end,
            )
        except Exception:
            stats["api_errors"] += 1
            logger.exception(
                "policyNewsList 실패 %s~%s",
                chunk_start,
                chunk_end,
            )
            continue

        for item in items:
            if limit is not None and stats["documents"] >= limit:
                return documents, stats

            stats["list_items"] += 1
            news_id = str(item.get("NewsItemId") or "").strip()
            if not news_id:
                stats["skipped_invalid"] += 1
                continue
            if news_id in seen_ids:
                stats["skipped_duplicate"] += 1
                continue
            seen_ids.add(news_id)

            if is_embargo_active(item.get("EmbargoDate")):
                stats["skipped_embargo"] += 1
                continue

            row = build_policy_document_row(item)
            if row is None:
                stats["skipped_invalid"] += 1
                continue

            documents.append(row)
            stats["documents"] += 1
            logger.info(
                "수집 [%d] %s (%s)",
                stats["documents"],
                row["pin_title"][:40],
                news_id,
            )

    return documents, stats


async def _main_async(args: argparse.Namespace) -> None:
    start = validate_yyyymmdd(args.start_date, label="start_date")
    end = validate_yyyymmdd(args.end_date, label="end_date")
    if start > end:
        raise ValueError("start_date는 end_date보다 이후일 수 없습니다.")

    output = Path(args.output) if args.output else DEFAULT_OUTPUT
    async with PolicyNewsClient.from_settings() as client:
        documents, stats = await fetch_policy_documents(
            client=client,
            start_date=start,
            end_date=end,
            limit=args.limit,
        )

    write_jsonl(output, documents)
    print(f"저장: {output} ({len(documents)}건)")
    print(f"stats: {stats}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="정책뉴스 OpenAPI 수집")
    parser.add_argument("--start-date", required=True, help="YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="YYYYMMDD")
    parser.add_argument("--limit", type=int, default=None, help="최대 수집 건수")
    parser.add_argument("--output", default=None, help="출력 JSONL 경로")
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
