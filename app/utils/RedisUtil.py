from __future__ import annotations

from typing import Literal, overload

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings


def _resolve_redis_config() -> tuple[str, int, int, str | None]:
    if settings.env == "local":
        host = settings.redis_local_host or "localhost"
        port = settings.redis_local_port or 6379
        db = 0
        password = None
        return host, port, db, password

    host = settings.redis_aws_host or "localhost"
    port = settings.redis_aws_port or 6379
    db = settings.redis_aws_db or 0
    password = (
        settings.redis_aws_password.get_secret_value()
        if settings.redis_aws_password
        else None
    )
    return host, port, db, password


@overload
def get_redis_client(async_mode: Literal[False] = False) -> Redis: ...


@overload
def get_redis_client(async_mode: Literal[True]) -> AsyncRedis: ...


def get_redis_client(async_mode: bool = False) -> Redis | AsyncRedis:
    host, port, db, password = _resolve_redis_config()
    kwargs = {
        "host": host,
        "port": port,
        "db": db,
        "password": password,
        "decode_responses": True,
    }
    if async_mode:
        return AsyncRedis(**kwargs)
    return Redis(**kwargs)