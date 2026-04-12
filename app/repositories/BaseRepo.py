from __future__ import annotations

from typing import Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepo(Generic[T]):

    def __init__(self, session: AsyncSession, model: Type[T]) -> None:
        self._session = session
        self.model = model

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def save(self, entity: T, *, flush_immediately: bool = True) -> T:
        self.session.add(entity)
        if flush_immediately:
            await self.session.flush()
        return entity

    async def save_all(self, entities: list[T]) -> list[T]:
        self.session.add_all(entities)
        await self.session.flush()
        return entities

    async def get_by_id(self, id_: int | str) -> T | None:
        return await self.session.get(self.model, id_)

    async def get_all(self) -> list[T]:
        result = await self.session.execute(select(self.model))
        return list(result.scalars().all())

    async def remove(self, entity: T) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def flush(self) -> None:
        await self.session.flush()
