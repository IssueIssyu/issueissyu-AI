from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.EventPin import EventPin
from app.models.Pin import Pin
from app.repositories.BaseRepo import BaseRepo

_EVENT_PIN_LOAD_OPTIONS = (
    selectinload(EventPin.pin).selectinload(Pin.pin_images),
    selectinload(EventPin.pin).selectinload(Pin.pin_location),
)


class EventPinRepo(BaseRepo[EventPin]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EventPin)

    async def get_by_festival_api_id(self, festival_api_id: int) -> EventPin | None:
        result = await self.session.execute(
            select(EventPin)
            .where(EventPin.festival_api_id == festival_api_id)
            .options(*_EVENT_PIN_LOAD_OPTIONS),
        )
        return result.scalar_one_or_none()

    async def list_festival_api_ids(self) -> set[int]:
        result = await self.session.execute(
            select(EventPin.festival_api_id).where(EventPin.festival_api_id.is_not(None)),
        )
        return {int(row) for row in result.scalars().all() if row is not None}

    async def count_festival_pins(self) -> int:
        result = await self.session.execute(
            select(func.count(EventPin.event_pin_id)).where(
                EventPin.festival_api_id.is_not(None),
            ),
        )
        return result.scalar_one()

    async def get_by_policy_api_id(self, policy_api_id: int) -> EventPin | None:
        result = await self.session.execute(
            select(EventPin)
            .where(EventPin.policy_api_id == policy_api_id)
            .options(*_EVENT_PIN_LOAD_OPTIONS),
        )
        return result.scalar_one_or_none()

    async def list_policy_api_ids(self) -> set[int]:
        result = await self.session.execute(
            select(EventPin.policy_api_id).where(EventPin.policy_api_id.is_not(None)),
        )
        return {int(row) for row in result.scalars().all() if row is not None}

    async def count_policy_pins(self) -> int:
        result = await self.session.execute(
            select(func.count(EventPin.event_pin_id)).where(
                EventPin.policy_api_id.is_not(None),
            ),
        )
        return result.scalar_one()
