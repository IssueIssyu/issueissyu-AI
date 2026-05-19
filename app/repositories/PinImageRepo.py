from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.PinImage import PinImage
from app.repositories.BaseRepo import BaseRepo


class PinImageRepo(BaseRepo[PinImage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PinImage)

    async def list_by_pin_id(self, pin_id: int) -> list[PinImage]:
        result = await self.session.execute(
            select(PinImage)
            .where(PinImage.pin_id == pin_id)
            .order_by(PinImage.is_main.desc(), PinImage.pin_image_id.asc()),
        )
        return list(result.scalars().all())
