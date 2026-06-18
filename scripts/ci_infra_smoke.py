"""CI infrastructure smoke test: PostgreSQL, Redis, S3."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import asyncpg
import boto3
from dotenv import dotenv_values
from redis import Redis


def get_env_value(env: dict[str, str | None], *keys: str, required: bool = False) -> str | None:
    for key in keys:
        value = env.get(key) or os.getenv(key)
        if value:
            return value
    if required:
        joined_keys = ", ".join(keys)
        raise RuntimeError(f"Missing required env key: {joined_keys}")
    return None


async def check_postgres() -> None:
    conn = await asyncpg.connect(
        user=os.getenv("LOCAL_DB_USER", "postgres"),
        password=os.getenv("LOCAL_DB_PASSWORD", "postgres"),
        database=os.getenv("LOCAL_DB_NAME", "app"),
        host=os.getenv("LOCAL_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("LOCAL_DB_PORT", "5432")),
    )
    try:
        result = await conn.fetchval("SELECT 1;")
        assert result == 1
    finally:
        await conn.close()


def check_redis(env: dict[str, str | None]) -> None:
    redis_host = get_env_value(env, "REDIS_LOCAL_HOST", "LOCAL_REDIS_HOST") or "localhost"
    redis_port = int(get_env_value(env, "REDIS_LOCAL_PORT", "LOCAL_REDIS_PORT") or "6379")
    redis_client = Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
    assert redis_client.ping() is True


def check_s3(env: dict[str, str | None]) -> None:
    aws_access_key = get_env_value(env, "AWS_ACCESS_KEY", required=True)
    aws_secret_key = get_env_value(env, "AWS_SECRET_KEY", required=True)
    aws_region = get_env_value(env, "AWS_REGION", required=True)
    aws_bucket = get_env_value(env, "AWS_BUCKET", required=True)

    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )
    s3.head_bucket(Bucket=aws_bucket)
    key = f"ci-smoke/{uuid.uuid4().hex}.txt"
    body = b"ci-smoke-test"
    s3.put_object(Bucket=aws_bucket, Key=key, Body=body, ContentType="text/plain")
    obj = s3.get_object(Bucket=aws_bucket, Key=key)
    assert obj["Body"].read() == body
    s3.delete_object(Bucket=aws_bucket, Key=key)


def main() -> int:
    env = dotenv_values(".env")
    asyncio.run(check_postgres())
    check_redis(env)
    check_s3(env)
    print("infra smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
