from __future__ import annotations

from app.core.codes import ErrorCode
from app.core.exceptions import raise_business_exception
from app.models.User import User
from app.repositories.UserRepo import UserRepo
from app.schemas.UserDTO import UserDTO


class UserService:
    def __init__(self, user_repo: UserRepo) -> None:
        self.user_repo = user_repo

    async def get_user(self, uid: str) -> UserDTO:
        user = await self.user_repo.get_by_uid(uid)
        if user is None:
            raise_business_exception(ErrorCode.USER_NOT_FOUND)
        return UserDTO.model_validate(user)

    async def get_user_entity(self, uid: str) -> User:
        user = await self.user_repo.get_by_uid(uid)
        if user is None:
            raise_business_exception(ErrorCode.USER_NOT_FOUND)
        return user
