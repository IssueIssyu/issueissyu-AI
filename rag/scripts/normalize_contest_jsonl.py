"""
기존 contest_documents.jsonl 의 NBSP/ZWSP·UI 잡음 정리 (재크롤 없이).

  python -m rag.scripts.normalize_contest_jsonl
  python -m rag.scripts.normalize_contest_jsonl --path rag/output/contest_documents.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rag.scripts.chunk_module import iter_jsonl, write_jsonl
from rag.scripts.fetch_linkareer_contests import CONTEST_DOCUMENTS_PATH, normalize_contest_row


def main() -> None:
    parser = argparse.ArgumentParser(description="contest_documents.jsonl 유니코드 공백 정리")
    parser.add_argument(
        "--path",
        type=Path,
        default=CONTEST_DOCUMENTS_PATH,
        help="대상 JSONL",
    )
    args = parser.parse_args()
    path: Path = args.path
    if not path.is_file():
        raise SystemExit(f"파일 없음: {path}")

    rows = [normalize_contest_row(row) for row in iter_jsonl(path) if isinstance(row, dict)]
    write_jsonl(path, rows)
    print(f"정리 완료: {path} ({len(rows)}건)")


if __name__ == "__main__":
    main()
