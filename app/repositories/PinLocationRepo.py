from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.PinLocation import PinLocation
from app.repositories.BaseRepo import BaseRepo


class PinLocationRepo(BaseRepo[PinLocation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PinLocation)
