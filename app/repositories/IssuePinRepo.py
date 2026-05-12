from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.IssuePin import IssuePin
from app.repositories.BaseRepo import BaseRepo


class IssuePinRepo(BaseRepo[IssuePin]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, IssuePin)

    async def get_by_pin_id(self, pin_id: int) -> IssuePin | None:
        result = await self.session.execute(
            select(IssuePin).where(IssuePin.pin_id == pin_id)
        )
        return result.scalar_one_or_none()
