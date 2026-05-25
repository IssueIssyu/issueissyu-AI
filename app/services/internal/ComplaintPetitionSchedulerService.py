from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from app.core.database import AsyncSessionLocal
from app.repositories.ComplaintPetitionRepo import ComplaintPetitionRepo
from app.repositories.DepartmentRepo import DepartmentRepo
from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.LocationDepartmentRepo import LocationDepartmentRepo
from app.repositories.LocationRepo import LocationRepo
from app.repositories.UserRepo import UserRepo
from app.services.ComplaintEmailService import ComplaintEmailService
from app.services.ComplaintPetitionService import ComplaintPetitionService
from app.utils.S3Util import S3Util

logger = logging.getLogger(__name__)
_KST = ZoneInfo("Asia/Seoul")


class ComplaintPetitionSchedulerService:
    def __init__(
        self,
        *,
        complaint_email_service: ComplaintEmailService,
        s3_util: S3Util,
    ) -> None:
        self._complaint_email_service = complaint_email_service
        self._s3_util = s3_util
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="complaint_petition_scheduler")
        logger.info("민원 자동 생성 스케줄러 시작")

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
        logger.info("민원 자동 생성 스케줄러 종료")

    async def run_once_now(self) -> dict[str, int]:
        async with AsyncSessionLocal() as session:
            service = ComplaintPetitionService(
                complaint_email_service=self._complaint_email_service,
                issue_pin_repo=IssuePinRepo(session),
                location_department_repo=LocationDepartmentRepo(session),
                complaint_petition_repo=ComplaintPetitionRepo(session),
                department_repo=DepartmentRepo(session),
                location_repo=LocationRepo(session),
                user_repo=UserRepo(session),
                s3_util=self._s3_util,
            )
            try:
                result = await service.create_scheduled_petitions(threshold=30)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    async def _run_loop(self) -> None:
        while True:
            wait_seconds = self._seconds_until_next_midnight_kst()
            logger.info("민원 자동 생성 스케줄러 대기 %.1fs", wait_seconds)
            await asyncio.sleep(wait_seconds)
            try:
                result = await self.run_once_now()
                logger.info("민원 자동 생성 스케줄 실행 결과: %s", result)
            except Exception:
                logger.exception("민원 자동 생성 스케줄 실행 실패")

    @staticmethod
    def _seconds_until_next_midnight_kst() -> float:
        now = datetime.now(_KST)
        tomorrow = now.date() + timedelta(days=1)
        next_midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=_KST)
        delta = next_midnight - now
        return max(delta.total_seconds(), 1.0)

