from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.Department import Department
from app.models.LocationDepartment import LocationDepartment
from app.repositories.BaseRepo import BaseRepo


class LocationDepartmentRepo(BaseRepo[LocationDepartment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LocationDepartment)

    async def get_by_location_and_department_name(
        self,
        *,
        location_id: int,
        department_name: str,
    ) -> LocationDepartment | None:
        result = await self.session.execute(
            select(LocationDepartment)
            .join(Department, Department.department_id == LocationDepartment.department_id)
            .where(
                LocationDepartment.location_id == location_id,
                Department.department_name == department_name,
            )
            .options(
                selectinload(LocationDepartment.department),
                selectinload(LocationDepartment.location),
            ),
        )
        return result.scalar_one_or_none()

    async def list_active_by_location(self, location_id: int) -> list[LocationDepartment]:
        result = await self.session.execute(
            select(LocationDepartment)
            .where(
                LocationDepartment.location_id == location_id,
                LocationDepartment.is_active.is_(True),
            )
            .options(selectinload(LocationDepartment.department))
            .order_by(LocationDepartment.location_department_id.asc()),
        )
        return list(result.scalars().all())

    async def get_by_location_and_department_id(
        self,
        *,
        location_id: int,
        department_id: int,
    ) -> LocationDepartment | None:
        result = await self.session.execute(
            select(LocationDepartment).where(
                LocationDepartment.location_id == location_id,
                LocationDepartment.department_id == department_id,
            ),
        )
        return result.scalar_one_or_none()

    async def list_existing_pair_keys(
        self,
        *,
        location_ids: list[int],
        department_ids: list[int],
    ) -> set[tuple[int, int]]:
        if not location_ids or not department_ids:
            return set()

        result = await self.session.execute(
            select(
                LocationDepartment.location_id,
                LocationDepartment.department_id,
            ).where(
                LocationDepartment.location_id.in_(location_ids),
                LocationDepartment.department_id.in_(department_ids),
            ),
        )
        return {(int(row[0]), int(row[1])) for row in result.fetchall()}

