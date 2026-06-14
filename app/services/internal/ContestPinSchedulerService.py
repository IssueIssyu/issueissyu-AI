from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.CardnewsImageS3Repo import CardnewsImageS3Repo
from app.repositories.CommunityRepo import CommunityRepo
from app.repositories.EventPinRepo import EventPinRepo
from app.repositories.PinImageRepo import PinImageRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.ContestAdminDTO import ContestSyncResult
from app.services.ContestEventIngestService import ContestEventIngestService
from app.services.ContestPinService import ContestPinService
from app.utils.S3Util import S3Util

logger = logging.getLogger(__name__)
_KST = ZoneInfo("Asia/Seoul")


class ContestPinSchedulerService:
    def __init__(self, *, s3_util: S3Util) -> None:
        self._s3_util = s3_util
        self._task: asyncio.Task[None] | None = None
        self._pin_service = ContestPinService()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="contest_pin_scheduler")
        logger.info("공모전 핀 sync 스케줄러 시작")

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
        logger.info("공모전 핀 sync 스케줄러 종료")

    async def run_once_now(
        self,
        *,
        force: bool = False,
        max_pages: int | None = None,
        start_page: int | None = None,
    ) -> ContestSyncResult:
        async with AsyncSessionLocal() as session:
            ingest = ContestEventIngestService(
                pin_repo=PinRepo(session),
                event_pin_repo=EventPinRepo(session),
                community_repo=CommunityRepo(session),
                cardnews_image_s3_repo=CardnewsImageS3Repo(session),
                pin_image_repo=PinImageRepo(session),
                user_repo=UserRepo(session),
            )
            return await self._pin_service.sync_pipeline(
                ingest_service=ingest,
                s3_util=self._s3_util,
                max_pages=max_pages,
                start_page=start_page,
            )

    async def _run_loop(self) -> None:
        while True:
            wait_seconds = self._seconds_until_next_schedule_kst()
            logger.info("공모전 핀 sync 스케줄러 대기 %.1fs", wait_seconds)
            await asyncio.sleep(wait_seconds)
            try:
                result = await self.run_once_now(force=False)
                logger.info(
                    "공모전 핀 sync 실행: 가공 %d건, INSERT %d건",
                    result.transform.processed_count,
                    result.import_result.inserted_count,
                )
            except Exception:
                logger.exception("공모전 핀 sync 스케줄 실행 실패")

    @staticmethod
    def _seconds_until_next_schedule_kst() -> float:
        now = datetime.now(_KST)
        hour = settings.contest_sync_schedule_hour_kst
        next_run = datetime.combine(now.date(), datetime.min.time(), tzinfo=_KST) + timedelta(hours=hour)
        if now >= next_run:
            next_run += timedelta(days=1)
        delta = next_run - now
        return max(delta.total_seconds(), 1.0)
