from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ComplaintPetition import ComplaintPetition
from app.models.IssuePin import IssuePin
from app.models.LocationDepartment import LocationDepartment
from app.models.enum.ComplaintPetitionStatus import ComplaintPetitionStatus
from app.repositories.BaseRepo import BaseRepo


class ComplaintPetitionRepo(BaseRepo[ComplaintPetition]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ComplaintPetition)

    @staticmethod
    def _review_load_options():
        return (
            selectinload(ComplaintPetition.location_department).selectinload(LocationDepartment.department),
            selectinload(ComplaintPetition.location_department).selectinload(LocationDepartment.location),
            selectinload(ComplaintPetition.issue_pin).selectinload(IssuePin.pin),
        )

    async def exists_by_issue_pin_and_generated_on(
        self,
        *,
        issue_pin_id: int,
        generated_on: date,
    ) -> bool:
        result = await self.session.execute(
            select(ComplaintPetition.petition_id).where(
                ComplaintPetition.issue_pin_id == issue_pin_id,
                ComplaintPetition.generated_on == generated_on,
            ),
        )
        return result.scalar_one_or_none() is not None

    async def has_active_petition(self, *, issue_pin_id: int) -> bool:
        result = await self.session.execute(
            select(ComplaintPetition.petition_id).where(
                ComplaintPetition.issue_pin_id == issue_pin_id,
                ComplaintPetition.status != ComplaintPetitionStatus.FAILED.value,
            ).limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def get_by_petition_ids(self, petition_ids: list[int]) -> list[ComplaintPetition]:
        if not petition_ids:
            return []
        result = await self.session.execute(
            select(ComplaintPetition)
            .where(ComplaintPetition.petition_id.in_(petition_ids))
            .options(*self._review_load_options()),
        )
        return list(result.scalars().all())

    async def list_for_admin(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ComplaintPetition], int]:
        filters = []
        if status is not None:
            filters.append(ComplaintPetition.status == status)

        count_stmt = select(func.count()).select_from(ComplaintPetition)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_result = await self.session.execute(count_stmt)
        total = int(total_result.scalar_one())

        list_stmt = (
            select(ComplaintPetition)
            .options(*self._review_load_options())
            .order_by(ComplaintPetition.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if filters:
            list_stmt = list_stmt.where(*filters)
        result = await self.session.execute(list_stmt)
        return list(result.scalars().all()), total

    async def get_by_petition_id_for_review(self, petition_id: int) -> ComplaintPetition | None:
        result = await self.session.execute(
            select(ComplaintPetition)
            .where(ComplaintPetition.petition_id == petition_id)
            .options(*self._review_load_options()),
        )
        return result.scalar_one_or_none()

    async def update_status(self, *, petition_id: int, status: str) -> bool:
        result = await self.session.execute(
            update(ComplaintPetition)
            .where(ComplaintPetition.petition_id == petition_id)
            .values(status=status),
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0

