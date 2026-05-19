from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.PinLike import PinLike
from app.repositories.BaseRepo import BaseRepo


class PinLikeRepo(BaseRepo[PinLike]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PinLike)

    async def exists_like(self, *, pin_id: int, uid: str) -> bool:
        result = await self.session.execute(
            select(PinLike.pin_like_id)
            .where(PinLike.pin_id == pin_id, PinLike.uid == uid)
            .limit(1),
        )
        return result.scalar_one_or_none() is not None
