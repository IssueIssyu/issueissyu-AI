from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.Department import Department
from app.repositories.BaseRepo import BaseRepo


class DepartmentRepo(BaseRepo[Department]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Department)

    async def get_by_name(self, department_name: str) -> Department | None:
        result = await self.session.execute(
            select(Department).where(Department.department_name == department_name),
        )
        return result.scalar_one_or_none()

    async def get_all_ordered(self) -> list[Department]:
        result = await self.session.execute(
            select(Department).order_by(Department.department_name.asc()),
        )
        return list(result.scalars().all())

    async def get_by_names(self, names: list[str]) -> list[Department]:
        if not names:
            return []
        result = await self.session.execute(
            select(Department).where(Department.department_name.in_(names)),
        )
        return list(result.scalars().all())

