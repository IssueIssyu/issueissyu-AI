from typing import Annotated

from fastapi import Depends, Request
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db_session
from app.repositories.UserRepo import UserRepo
from app.services.UserService import UserService
from app.utils.RedisUtil import get_redis_client
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
        s3_util = S3Util()
        request.app.state.s3_util = s3_util
    return s3_util


S3UtilDep = Annotated[S3Util, Depends(get_s3_util)]


def get_sync_redis_client() -> Redis:
    return get_redis_client(async_mode=False)


def get_async_redis_client() -> AsyncRedis:
    return get_redis_client(async_mode=True)


SyncRedisDep = Annotated[Redis, Depends(get_sync_redis_client)]
AsyncRedisDep = Annotated[AsyncRedis, Depends(get_async_redis_client)]
