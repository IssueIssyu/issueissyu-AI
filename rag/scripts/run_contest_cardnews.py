"""
공모전 원문 JSONL → 텍스트 카드뉴스 PNG + contest_pins_for_db.jsonl

  python -m rag.scripts.run_contest_cardnews --limit 1
  python -m rag.scripts.run_contest_cardnews --contentid 319419 --no-caption
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from app.services.contest_pin_transform import transform_documents_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="공모전 카드뉴스 배치 생성")
    parser.add_argument("--limit", type=int, default=None, help="최대 처리 건수")
    parser.add_argument("--contentid", type=str, default=None, help="특정 activity ID만")
    parser.add_argument(
        "--no-caption",
        action="store_true",
        help="pin_content에 인스타 캡션 대신 정리된 원문 사용",
    )
    parser.add_argument("--model", type=str, default=None, help="Gemini 모델명")
    args = parser.parse_args()

    result = asyncio.run(
        transform_documents_jsonl(
            limit=args.limit,
            model=args.model,
            with_caption=not args.no_caption,
            contentid=args.contentid,
        ),
    )
    print(
        f"완료: {result.processed_count}건 성공, {result.error_count}건 오류 → {result.output_path}",
    )
    if result.errors:
        for err in result.errors:
            print(f"  - {err.get('contentid')}: {err.get('error')}", file=sys.stderr)
    return 0 if result.processed_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
