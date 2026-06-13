"""
policy_documents.jsonl → Gemini 쉬운 설명 pin_content 가공 → DB 적재용 JSONL

프로젝트 루트에서:
  python -m rag.scripts.transform_policy_content --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.config import settings
from app.services.policy_pin_transform import transform_documents_jsonl
from rag.scripts.preprocess_module import OUTPUT_DIR

logger = logging.getLogger(__name__)

DEFAULT_INPUT = OUTPUT_DIR / "policy_documents.jsonl"
DEFAULT_OUTPUT = OUTPUT_DIR / "policy_pins_for_db.jsonl"


async def run(args: argparse.Namespace) -> None:
    result = await transform_documents_jsonl(
        input_path=args.input,
        output_path=args.output,
        limit=args.limit,
        model=args.model,
    )

    preview_path = args.output.with_name("policy_pins_preview.json")
    preview_path.write_text(
        json.dumps(
            [p.model_dump() for p in result.pins[: min(3, len(result.pins))]],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = {
        "transformed_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(args.input),
        "output": str(args.output),
        "model": args.model or settings.gemini_pin_text_model,
        "processed": result.processed_count,
        "errors": result.errors,
        "error_count": result.error_count,
    }
    report_path = args.output.with_name("policy_transform_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"완료: {args.output} ({result.processed_count}건)")
    if result.errors:
        print(f"실패: {result.error_count}건 - {report_path}")
    print(f"미리보기: {preview_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="정책 pin_content → 쉬운 설명 본문(Gemini)")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None, help="처리 최대 건수")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini 모델 (기본: GEMINI_PIN_TEXT_MODEL)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
