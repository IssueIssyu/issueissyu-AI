from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.CardnewsImageS3 import CardnewsImageS3
from app.repositories.BaseRepo import BaseRepo


class CardnewsImageS3Repo(BaseRepo[CardnewsImageS3]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CardnewsImageS3)

    async def list_by_community_id(self, community_id: int) -> list[CardnewsImageS3]:
        result = await self.session.execute(
            select(CardnewsImageS3)
            .where(CardnewsImageS3.community_id == community_id)
            .order_by(CardnewsImageS3.cardnews_image_s3_id.asc()),
        )
        return list(result.scalars().all())

    async def delete_by_community_id(self, community_id: int) -> int:
        result = await self.session.execute(
            delete(CardnewsImageS3).where(CardnewsImageS3.community_id == community_id),
        )
        await self.session.flush()
        return int(result.rowcount or 0)
