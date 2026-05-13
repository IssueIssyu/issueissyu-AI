from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.Pin import Pin
from app.repositories.BaseRepo import BaseRepo


class PinRepo(BaseRepo[Pin]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Pin)
