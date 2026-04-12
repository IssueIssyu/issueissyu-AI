from __future__ import annotations

from uuid import UUID

from app.core.codes import ErrorCode
from app.core.exceptions import raise_business_exception
from app.models.User import User
from app.repositories.UserRepo import UserRepo
from app.schemas.UserDTO import UserDTO


class UserService:
    def __init__(self, user_repo: UserRepo) -> None:
        self.user_repo = user_repo

    async def get_user(self, uid: UUID) -> UserDTO:
        user = await self.user_repo.get_by_uid(uid)
        if user is None:
            raise_business_exception(ErrorCode.USER_NOT_FOUND)
        return UserDTO.model_validate(user)

    async def get_user_entity(self, uid: UUID) -> User:
        user = await self.user_repo.get_by_uid(uid)
        if user is None:
            raise_business_exception(ErrorCode.USER_NOT_FOUND)
        return user

    async def create_test_user(
        self,
        *,
        email: str = "test@issueissyu.ai",
        nickname: str = "tester",
        phone: str | None = None,
    ) -> UserDTO:
        existing = await self.user_repo.get_by_email(email)
        if existing is not None:
            return UserDTO.model_validate(existing)

        user = User(
            email=email,
            nickname=nickname,
            phone=phone,
            event_alarm_active=False,
            hot_alarm_active=False,
            store_alarm_active=False,
            like_alarm_active=False,
        )
        saved = await self.user_repo.save(user, flush_immediately=True)
        return UserDTO.model_validate(saved)

    async def get_all_users(self) -> list[UserDTO]:
        users = await self.user_repo.get_all_users()
        return [UserDTO.model_validate(user) for user in users]
