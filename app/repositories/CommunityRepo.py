from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.Community import Community
from app.repositories.BaseRepo import BaseRepo


class CommunityRepo(BaseRepo[Community]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Community)

    async def get_community_id_by_pin_id(self, pin_id: int) -> int | None:
        result = await self.session.execute(
            select(Community.community_id)
            .where(Community.pin_id == pin_id)
            .limit(1),
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    async def get_by_pin_id(self, pin_id: int) -> Community | None:
        result = await self.session.execute(
            select(Community).where(Community.pin_id == pin_id).limit(1),
        )
        return result.scalar_one_or_none()
