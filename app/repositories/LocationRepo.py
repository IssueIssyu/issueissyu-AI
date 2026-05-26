from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.Location import Location
from app.models.PopulationDensity import PopulationDensity
from app.repositories.BaseRepo import BaseRepo


class LocationRepo(BaseRepo[Location]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Location)

    async def get_all_ordered(self) -> list[Location]:
        result = await self.session.execute(
            select(Location).order_by(Location.location_id.asc()),
        )
        return list(result.scalars().all())

    async def get_target_petition_by_location_id(self, *, location_id: int) -> int | None:
        result = await self.session.execute(
            select(PopulationDensity.target_petition)
            .where(PopulationDensity.location_id == location_id)
            .limit(1),
        )
        value = result.scalar_one_or_none()
        if isinstance(value, int):
            return value
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

