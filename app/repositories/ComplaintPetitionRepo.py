from __future__ import annotations

from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ComplaintPetition import ComplaintPetition
from app.models.LocationDepartment import LocationDepartment
from app.models.enum.ComplaintPetitionStatus import ComplaintPetitionStatus
from app.repositories.BaseRepo import BaseRepo


class ComplaintPetitionRepo(BaseRepo[ComplaintPetition]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ComplaintPetition)

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
            .options(
                selectinload(ComplaintPetition.location_department).selectinload(LocationDepartment.department),
                selectinload(ComplaintPetition.location_department).selectinload(LocationDepartment.location),
                selectinload(ComplaintPetition.issue_pin),
            ),
        )
        return list(result.scalars().all())

    async def update_status(self, *, petition_id: int, status: str) -> bool:
        result = await self.session.execute(
            update(ComplaintPetition)
            .where(ComplaintPetition.petition_id == petition_id)
            .values(status=status),
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0

