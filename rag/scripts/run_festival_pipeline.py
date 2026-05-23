"""
축제 핀 배치 파이프라인 (Cron용)

  python -m rag.scripts.run_festival_pipeline
  python -m rag.scripts.run_festival_pipeline --start-date 20260501 --end-date 20261231 --fetch-limit 50

환경변수: VISITKOREA_SERVICE_KEY, GEMINI_API_KEY
선택: FESTIVAL_SYNC_LOOKAHEAD_DAYS, FESTIVAL_SYNC_FETCH_LIMIT
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.config import settings
from app.services.FestivalPinService import FestivalPinService
from rag.scripts.fetch_visitkorea import validate_yyyymmdd

logger = logging.getLogger(__name__)


def default_date_range() -> tuple[str, str]:
    today = date.today()
    end = today + timedelta(days=settings.festival_sync_lookahead_days)
    return today.strftime("%Y%m%d"), end.strftime("%Y%m%d")


async def run(args: argparse.Namespace) -> int:
    if args.start_date and args.end_date:
        start_date = validate_yyyymmdd(args.start_date, label="--start-date")
        end_date = validate_yyyymmdd(args.end_date, label="--end-date")
    else:
        start_date, end_date = default_date_range()

    if start_date > end_date:
        raise SystemExit("start-date는 end-date보다 이후일 수 없습니다.")

    fetch_limit = args.fetch_limit if args.fetch_limit is not None else settings.festival_sync_fetch_limit
    transform_limit = (
        args.transform_limit
        if args.transform_limit is not None
        else settings.festival_sync_transform_limit
    )

    service = FestivalPinService()

    logger.info("1/2 TourAPI 수집 %s ~ %s (limit=%s)", start_date, end_date, fetch_limit)
    search_result = await service.search_and_save(
        start_date=start_date,
        end_date=end_date,
        limit=fetch_limit,
        uncapped=True,
    )
    logger.info(
        "저장: %s (%d건)",
        search_result.saved_documents_path,
        search_result.count,
    )

    if args.skip_transform:
        logger.info("transform 생략 (--skip-transform)")
        return 0

    if search_result.count == 0:
        logger.warning("수집 0건 — transform 건너뜀")
        return 0

    logger.info("2/2 Gemini 가공 (limit=%s)", transform_limit)
    transform_result = await service.transform_and_save(limit=transform_limit)
    logger.info(
        "저장: %s (성공 %d건, 실패 %d건)",
        transform_result.output_path,
        transform_result.processed_count,
        transform_result.error_count,
    )

    report = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start_date,
        "end_date": end_date,
        "documents_path": search_result.saved_documents_path,
        "handoff_path": transform_result.output_path,
        "fetched": search_result.count,
        "transformed": transform_result.processed_count,
        "transform_errors": transform_result.error_count,
    }
    report_path = Path(search_result.saved_documents_path).with_name("festival_pipeline_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("리포트: %s", report_path)

    return 1 if transform_result.error_count else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="축제 핀 배치: fetch → transform (Cron)")
    parser.add_argument("--start-date", type=str, default=None, help="YYYYMMDD (미지정 시 오늘)")
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="YYYYMMDD (미지정 시 오늘+FESTIVAL_SYNC_LOOKAHEAD_DAYS)",
    )
    parser.add_argument("--fetch-limit", type=int, default=None, help="TourAPI 수집 최대 건수")
    parser.add_argument("--transform-limit", type=int, default=None, help="가공 최대 건수")
    parser.add_argument(
        "--skip-transform",
        action="store_true",
        help="수집만 (Gemini 생략)",
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
