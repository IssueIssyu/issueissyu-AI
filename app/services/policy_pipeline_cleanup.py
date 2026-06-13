from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.services.policy_cardnews import POLICY_CARDNEWS_OUTPUT_DIR
from app.services.policy_pin_transform import (
    POLICY_DOCUMENTS_PATH,
    POLICY_HANDOFF_PATH,
    load_jsonl_rows,
    parse_policy_api_id,
    row_content_id,
    write_handoff_map,
)
from rag.scripts.chunk_module import write_jsonl

logger = logging.getLogger(__name__)


def prune_jsonl_by_policy_api_ids(
    path: Path,
    policy_api_ids: set[int],
) -> int:
    if not policy_api_ids or not path.is_file():
        return 0

    kept: list[dict] = []
    removed = 0
    for row in load_jsonl_rows(path):
        policy_id = parse_policy_api_id(row)
        if policy_id is not None and policy_id in policy_api_ids:
            removed += 1
            continue
        kept.append(row)

    if removed > 0:
        write_jsonl(path, kept)
        logger.info("JSONL 정리 %s: %d건 제거, %d건 유지", path.name, removed, len(kept))
    return removed


def prune_pipeline_imported(
    policy_api_ids: set[int],
    *,
    documents_path: Path | None = None,
    handoff_path: Path | None = None,
) -> dict[str, int]:
    if not policy_api_ids:
        return {"documents_removed": 0, "handoff_removed": 0}

    docs = documents_path or POLICY_DOCUMENTS_PATH
    handoff = handoff_path or POLICY_HANDOFF_PATH
    return {
        "documents_removed": prune_jsonl_by_policy_api_ids(docs, policy_api_ids),
        "handoff_removed": prune_jsonl_by_policy_api_ids(handoff, policy_api_ids),
    }


def prune_handoff_pending_only(
    *,
    db_policy_api_ids: set[int],
    handoff_path: Path | None = None,
) -> int:
    """DB에 이미 있는 항목을 handoff에서 제거 (가공 완료·적재 완료 캐시 정리)."""
    path = handoff_path or POLICY_HANDOFF_PATH
    if not path.is_file() or not db_policy_api_ids:
        return 0
    return prune_jsonl_by_policy_api_ids(path, db_policy_api_ids)


def cleanup_local_cardnews_dirs(content_ids: set[str]) -> int:
    removed = 0
    for raw_id in content_ids:
        content_id = str(raw_id or "").strip()
        if not content_id:
            continue
        target = POLICY_CARDNEWS_OUTPUT_DIR / content_id
        if not target.is_dir():
            continue
        shutil.rmtree(target, ignore_errors=True)
        removed += 1
        logger.debug("로컬 카드뉴스 삭제: %s", target)
    return removed


def policy_api_ids_to_content_ids(policy_api_ids: set[int]) -> set[str]:
    return {str(policy_id) for policy_id in policy_api_ids}


def cleanup_after_policy_import(policy_api_ids: set[int]) -> dict[str, int]:
    stats = prune_pipeline_imported(policy_api_ids)
    stats["cardnews_dirs_removed"] = cleanup_local_cardnews_dirs(
        policy_api_ids_to_content_ids(policy_api_ids),
    )
    return stats


def reset_handoff_map(handoff_path: Path | None = None) -> None:
    write_handoff_map({}, handoff_path)


def content_ids_from_rows(rows: list[dict]) -> set[str]:
    out: set[str] = set()
    for row in rows:
        content_id = row_content_id(row)
        if content_id:
            out.add(content_id)
    return out
