from __future__ import annotations

from dataclasses import dataclass

# Spring `@RedisHash("token_redis")` + @Id = `uid:provider`와 동일한 도메인 모델.
# 실제 Redis 저장/갱신은 Java 백엔드가 담당하는 경우가 많고, 키만 맞춰야 할 때 쓰면 됨.

REDIS_HASH_NAME = "token_redis"


def refresh_token_id(uid: str, provider: str) -> str:
    """`uid:provider` 복합 id (Java `RefreshToken.id`)."""
    return f"{uid}:{provider}"


def refresh_token_doc_key(uid: str, provider: str) -> str:
    """
    Spring Data Redis `@RedisHash("token_redis")` + id 일 때 쓰는 키 형태에 맞춤.
    예: `token_redis:{uid}:{provider}` (환경/버전에 따라 prefix만 다를 수 있음)
    """
    return f"{REDIS_HASH_NAME}:{uid}:{provider}"


@dataclass(frozen=True, slots=True)
class RefreshToken:
    id: str
    refresh_token: str
    expiration: int  # TTL 초 (Java `@TimeToLive`)

    @staticmethod
    def create(
        uid: str,
        provider: str,
        token: str,
        ttl_seconds: int,
    ) -> RefreshToken:
        return RefreshToken(
            id=refresh_token_id(uid, provider),
            refresh_token=token,
            expiration=ttl_seconds,
        )
