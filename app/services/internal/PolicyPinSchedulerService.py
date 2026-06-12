from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.CardnewsImageS3Repo import CardnewsImageS3Repo
from app.repositories.CommunityRepo import CommunityRepo
from app.repositories.EventPinRepo import EventPinRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.PolicyAdminDTO import PolicySyncResult
from app.services.PolicyEventIngestService import PolicyEventIngestService, POLICY_SYNC_META_PATH
from app.services.PolicyPinService import PolicyPinService
from app.utils.S3Util import S3Util

logger = logging.getLogger(__name__)
_KST = ZoneInfo("Asia/Seoul")


class PolicyPinSchedulerService:
    def __init__(self, *, s3_util: S3Util) -> None:
        self._s3_util = s3_util
        self._task: asyncio.Task[None] | None = None
        self._pin_service = PolicyPinService()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="policy_pin_scheduler")
        logger.info("정책 핀 sync 스케줄러 시작")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("정책 핀 sync 스케줄러 종료")

    async def run_once_now(self, *, force: bool = False) -> PolicySyncResult:
        if not force and not self._should_run_sync():
            start, end = self._pin_service.default_date_range()
            from app.schemas.PolicyAdminDTO import PolicyImportBatchResult
            from app.schemas.PolicyPinDTO import PolicyPinSearchResult, PolicyPinTransformResult

            return PolicySyncResult(
                query_start_date=start,
                query_end_date=end,
                search=PolicyPinSearchResult(
                    query_start_date=start,
                    query_end_date=end,
                    count=0,
                    pins=[],
                    saved_documents_path=str(self._pin_service.documents_path()),
                    stats={},
                    hint="POLICY_SYNC_INTERVAL_DAYS 미경과로 sync 생략",
                ),
                transform=PolicyPinTransformResult(
                    input_path=str(self._pin_service.documents_path()),
                    output_path=str(self._pin_service.handoff_path()),
                    processed_count=0,
                    error_count=0,
                    pins=[],
                    hint="sync 생략",
                ),
                import_result=PolicyImportBatchResult(
                    inserted_count=0,
                    skipped_duplicate_count=0,
                    pending_import_count=0,
                    error_count=0,
                ),
                hint="POLICY_SYNC_INTERVAL_DAYS 미경과로 sync 생략",
            )

        async with AsyncSessionLocal() as session:
            ingest = PolicyEventIngestService(
                pin_repo=PinRepo(session),
                event_pin_repo=EventPinRepo(session),
                community_repo=CommunityRepo(session),
                cardnews_image_s3_repo=CardnewsImageS3Repo(session),
                user_repo=UserRepo(session),
            )
            return await self._pin_service.sync_pipeline(
                ingest_service=ingest,
                s3_util=self._s3_util,
            )

    def _should_run_sync(self) -> bool:
        if not POLICY_SYNC_META_PATH.is_file():
            return True
        try:
            meta = json.loads(POLICY_SYNC_META_PATH.read_text(encoding="utf-8"))
            last_sync_at = str(meta.get("last_sync_at") or "").strip()
            if not last_sync_at:
                return True
            last_run = datetime.fromisoformat(last_sync_at)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=_KST)
            elapsed = datetime.now(_KST) - last_run.astimezone(_KST)
            return elapsed >= timedelta(days=settings.policy_sync_interval_days)
        except (json.JSONDecodeError, ValueError):
            return True

    async def _run_loop(self) -> None:
        while True:
            wait_seconds = self._seconds_until_next_schedule_kst()
            logger.info("정책 핀 sync 스케줄러 대기 %.1fs", wait_seconds)
            await asyncio.sleep(wait_seconds)
            try:
                result = await self.run_once_now(force=False)
                logger.info(
                    "정책 핀 sync 실행: 가공 %d건, INSERT %d건",
                    result.transform.processed_count,
                    result.import_result.inserted_count,
                )
            except Exception:
                logger.exception("정책 핀 sync 스케줄 실행 실패")

    @staticmethod
    def _seconds_until_next_schedule_kst() -> float:
        now = datetime.now(_KST)
        hour = settings.policy_sync_schedule_hour_kst
        next_run = datetime.combine(now.date(), datetime.min.time(), tzinfo=_KST) + timedelta(hours=hour)
        if now >= next_run:
            next_run += timedelta(days=1)
        delta = next_run - now
        return max(delta.total_seconds(), 1.0)
