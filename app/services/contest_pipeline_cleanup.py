from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, TypedDict

from anyio import to_thread

from app.core.config import settings
from app.services.contest_cardnews import CONTEST_CARDNEWS_OUTPUT_DIR
from app.services.contest_pin_transform import (
    CONTEST_HANDOFF_PATH,
    load_jsonl_rows,
    parse_contest_api_id,
    row_content_id,
)
from rag.scripts.chunk_module import write_jsonl
from rag.scripts.fetch_linkareer_contests import CONTEST_DOCUMENTS_PATH

logger = logging.getLogger(__name__)


def prune_jsonl_by_contest_api_ids(
    path: Path,
    contest_api_ids: set[int],
) -> int:
    if not contest_api_ids or not path.is_file():
        return 0

    kept: list[dict] = []
    removed = 0
    for row in load_jsonl_rows(path):
        contest_id = parse_contest_api_id(row)
        if contest_id is not None and contest_id in contest_api_ids:
            removed += 1
            continue
        kept.append(row)

    if removed > 0:
        write_jsonl(path, kept)
        logger.info("JSONL 정리 %s: %d건 제거, %d건 유지", path.name, removed, len(kept))
    return removed


def prune_pipeline_imported(
    contest_api_ids: set[int],
    *,
    documents_path: Path | None = None,
    handoff_path: Path | None = None,
) -> dict[str, int]:
    if not contest_api_ids:
        return {"documents_removed": 0, "handoff_removed": 0}

    docs = documents_path or CONTEST_DOCUMENTS_PATH
    handoff = handoff_path or CONTEST_HANDOFF_PATH
    return {
        "documents_removed": prune_jsonl_by_contest_api_ids(docs, contest_api_ids),
        "handoff_removed": prune_jsonl_by_contest_api_ids(handoff, contest_api_ids),
    }


def cleanup_local_cardnews_dirs(content_ids: set[str]) -> int:
    removed = 0
    for raw_id in content_ids:
        content_id = str(raw_id or "").strip()
        if not content_id:
            continue
        target = CONTEST_CARDNEWS_OUTPUT_DIR / content_id
        if not target.is_dir():
            continue
        shutil.rmtree(target, ignore_errors=True)
        removed += 1
        logger.debug("로컬 카드뉴스 삭제: %s", target)
    return removed


def contest_api_ids_to_content_ids(contest_api_ids: set[int]) -> set[str]:
    return {str(contest_id) for contest_id in contest_api_ids}


def cleanup_after_contest_import(contest_api_ids: set[int]) -> dict[str, int]:
    stats = prune_pipeline_imported(contest_api_ids)
    stats["cardnews_dirs_removed"] = cleanup_local_cardnews_dirs(
        contest_api_ids_to_content_ids(contest_api_ids),
    )
    return stats
