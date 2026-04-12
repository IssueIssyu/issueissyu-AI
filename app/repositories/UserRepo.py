from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.User import User
from app.repositories.BaseRepo import BaseRepo


class UserRepo(BaseRepo[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_uid(self, uid: UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.uid == uid)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_all_users(self) -> list[User]:
        return await self.get_all()
