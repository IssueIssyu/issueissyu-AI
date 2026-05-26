from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.IssuePin import IssuePin
from app.models.Pin import Pin
from app.models.PinLocation import PinLocation
from app.models.PopulationDensity import PopulationDensity
from app.models.enum.IssuePinState import IssuePinState
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

    async def list_by_petition_count_gte(
        self,
        *,
        threshold: int,
        limit: int = 200,
        offset: int = 0,
    ) -> list[IssuePin]:
        result = await self.session.execute(
            select(IssuePin)
            .where(IssuePin.petition_count >= threshold)
            .options(*_ISSUE_PIN_LOAD_OPTIONS)
            .order_by(IssuePin.issue_pin_id.asc())
            .limit(limit)
            .offset(offset),
        )
        return list(result.scalars().all())

    async def list_by_target_petition(
        self,
        *,
        default_threshold: int = 30,
        limit: int = 200,
        offset: int = 0,
    ) -> list[IssuePin]:
        id_result = await self.session.execute(
            select(IssuePin.issue_pin_id)
            .join(PinLocation, PinLocation.pin_id == IssuePin.pin_id)
            .outerjoin(PopulationDensity, PopulationDensity.location_id == PinLocation.location_id)
            .where(
                IssuePin.issue_pin_state == IssuePinState.BEFORE_PROGRESS,
                IssuePin.petition_count
                >= func.coalesce(PopulationDensity.target_petition, default_threshold),
            )
            .order_by(IssuePin.issue_pin_id.asc())
            .limit(limit)
            .offset(offset),
        )
        issue_pin_ids = [int(row[0]) for row in id_result.fetchall()]
        if not issue_pin_ids:
            return []

        result = await self.session.execute(
            select(IssuePin)
            .where(IssuePin.issue_pin_id.in_(issue_pin_ids))
            .options(*_ISSUE_PIN_LOAD_OPTIONS),
        )
        by_id = {row.issue_pin_id: row for row in result.scalars().all()}
        return [by_id[issue_pin_id] for issue_pin_id in issue_pin_ids if issue_pin_id in by_id]

    async def update_state(self, issue_pin_id: int, state: IssuePinState) -> bool:
        result = await self.session.execute(
            update(IssuePin)
            .where(IssuePin.issue_pin_id == issue_pin_id)
            .values(issue_pin_state=state),
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0

    async def reset_confidence(self, issue_pin_id: int) -> bool:
        result = await self.session.execute(
            update(IssuePin)
            .where(IssuePin.issue_pin_id == issue_pin_id)
            .values(
                issue_confidence=None,
                confidence_content=None,
            ),
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0
