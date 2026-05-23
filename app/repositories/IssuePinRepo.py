from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.IssuePin import IssuePin
from app.models.Pin import Pin
from app.repositories.BaseRepo import BaseRepo

_ISSUE_PIN_LOAD_OPTIONS = (
    selectinload(IssuePin.pin).selectinload(Pin.pin_images),
    selectinload(IssuePin.pin).selectinload(Pin.pin_location),
    selectinload(IssuePin.pin).selectinload(Pin.user),
)


class IssuePinRepo(BaseRepo[IssuePin]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, IssuePin)

    async def get_by_pin_id(self, pin_id: int) -> IssuePin | None:
        result = await self.session.execute(
            select(IssuePin)
            .where(IssuePin.pin_id == pin_id)
            .options(*_ISSUE_PIN_LOAD_OPTIONS),
        )
        return result.scalar_one_or_none()

    async def get_by_issue_pin_id(self, issue_pin_id: int) -> IssuePin | None:
        result = await self.session.execute(
            select(IssuePin)
            .where(IssuePin.issue_pin_id == issue_pin_id)
            .options(*_ISSUE_PIN_LOAD_OPTIONS),
        )
        return result.scalar_one_or_none()

    async def update_confidence(
        self,
        issue_pin_id: int,
        *,
        issue_confidence: float,
        confidence_content: str,
    ) -> bool:
        result = await self.session.execute(
            update(IssuePin)
            .where(IssuePin.issue_pin_id == issue_pin_id)
            .values(
                issue_confidence=issue_confidence,
                confidence_content=confidence_content,
            ),
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0
