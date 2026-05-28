from __future__ import annotations

from sqlalchemy import delete, select
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

    async def get_by_pin_id_and_url(self, pin_id: int, pin_s3_url: str) -> PinImage | None:
        normalized_url = pin_s3_url.strip()
        if not normalized_url:
            return None
        result = await self.session.execute(
            select(PinImage).where(
                PinImage.pin_id == pin_id,
                PinImage.pin_s3_url == normalized_url,
            ),
        )
        return result.scalar_one_or_none()

    async def delete_by_ids(self, pin_image_ids: list[int]) -> int:
        if not pin_image_ids:
            return 0
        result = await self.session.execute(
            delete(PinImage).where(PinImage.pin_image_id.in_(pin_image_ids)),
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def delete_by_pin_id(self, pin_id: int) -> int:
        result = await self.session.execute(
            delete(PinImage).where(PinImage.pin_id == pin_id),
        )
        await self.session.flush()
        return int(result.rowcount or 0)
