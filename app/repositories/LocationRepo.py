from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.Location import Location
from app.repositories.BaseRepo import BaseRepo


class LocationRepo(BaseRepo[Location]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Location)

    async def get_all_ordered(self) -> list[Location]:
        result = await self.session.execute(
            select(Location).order_by(Location.location_id.asc()),
        )
        return list(result.scalars().all())

