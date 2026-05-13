"""임베딩 벡터 연산 유틸 + PostgreSQL `vector` 확장 보장."""

from __future__ import annotations

import math
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_EMBEDDING_DIM = 1536


async def ensure_pgvector_extension(session: AsyncSession) -> None:
    """DB에 `vector` 확장이 없으면 `CREATE EXTENSION IF NOT EXISTS vector` 실행."""
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await session.flush()


def assert_embedding_dim(
    vec: Sequence[float],
    dim: int | None = None,
) -> list[float]:
    """길이 검증 후 `list[float]`로 반환. `dim`이 없으면 `DEFAULT_EMBEDDING_DIM`을 사용한다."""
    expected = DEFAULT_EMBEDDING_DIM if dim is None else dim
    if len(vec) != expected:
        msg = f"임베딩 차원은 {expected}이어야 하는데 {len(vec)}입니다."
        raise ValueError(msg)
    return [float(x) for x in vec]


def l2_normalize(vec: Sequence[float]) -> list[float]:
    """L2 단위 벡터 (길이 0이면 그대로 반환)."""
    out = [float(x) for x in vec]
    s = math.sqrt(sum(x * x for x in out))
    if s == 0.0:
        return out
    return [x / s for x in out]


def l2_norm(vec: Sequence[float]) -> float:
    """유클리드 노름."""
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def inner_product(a: Sequence[float], b: Sequence[float]) -> float:
    """내적. 길이가 다르면 `ValueError`."""
    if len(a) != len(b):
        msg = f"내적은 길이가 같아야 합니다: {len(a)} vs {len(b)}"
        raise ValueError(msg)
    return sum(float(x) * float(y) for x, y in zip(a, b))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """코사인 유사도 ∈ [-1, 1]. 한쪽 노름이 0이면 `ValueError`."""
    na = l2_norm(a)
    nb = l2_norm(b)
    if na == 0.0 or nb == 0.0:
        raise ValueError("코사인 유사도는 영벡터에 정의되지 않습니다.")
    return inner_product(a, b) / (na * nb)


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """pgvector `cosine_distance`와 맞추기: 1 - cos_sim."""
    return 1.0 - cosine_similarity(a, b)
