from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db_session
from app.login.http_auth import get_current_user_id, get_optional_user_id
from app.models.User import User
from app.repositories.UserRepo import UserRepo
from app.services.UserService import UserService
from app.utils.S3Util import S3Util


DbSessionDep = Annotated[AsyncSession, Depends(get_async_db_session)]


def get_user_repo(session: DbSessionDep) -> UserRepo:
    return UserRepo(session)


UserRepoDep = Annotated[UserRepo, Depends(get_user_repo)]


def get_user_service(user_repo: UserRepoDep) -> UserService:
    return UserService(user_repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_s3_util(request: Request) -> S3Util:
    s3_util = getattr(request.app.state, "s3_util", None)
    if s3_util is None:
        raise RuntimeError("S3Util is not initialized. Check application lifespan setup.")
    return s3_util


S3UtilDep = Annotated[S3Util, Depends(get_s3_util)]


def get_async_redis_client(request: Request) -> AsyncRedis:
    redis_client = getattr(request.app.state, "async_redis_client", None)
    if redis_client is None:
        raise RuntimeError("Async Redis client is not initialized. Check application lifespan setup.")
    return redis_client


AsyncRedisDep = Annotated[AsyncRedis, Depends(get_async_redis_client)]

CurrentUserIdDep = Annotated[UUID, Depends(get_current_user_id)]
OptionalUserIdDep = Annotated[UUID | None, Depends(get_optional_user_id)]


async def get_current_user(
    uid: CurrentUserIdDep,
    user_repo: UserRepoDep,
) -> User:
    u = await user_repo.get_by_uid(uid)
    if u is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return u


CurrentUserDep = Annotated[User, Depends(get_current_user)]
