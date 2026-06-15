from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.config import Settings


class VectorDomain(str, Enum):
    COMPLAINT = "complaint"
    FESTIVAL = "festival"
    POLICY = "policy"
    CONTEST = "contest"


@dataclass(frozen=True, slots=True)
class DomainVectorConfig:
    table_name: str
    embedding_model: str
    embed_dim: int
    # True면 table_name을 pgvector 테이블 전체명으로 사용(complaint_chunks_ 접두사 없음)
    standalone_table: bool = False


def build_vector_domain_configs(settings: Settings) -> dict[VectorDomain, DomainVectorConfig]:
    embedding_model = settings.gemini_embedding_model
    embed_dim = settings.vector_embed_dim
    return {
        VectorDomain.COMPLAINT: DomainVectorConfig(
            table_name="complaint",
            embedding_model=embedding_model,
            embed_dim=embed_dim,
            standalone_table=False,
        ),
        VectorDomain.FESTIVAL: DomainVectorConfig(
            table_name="festival",
            embedding_model=embedding_model,
            embed_dim=embed_dim,
            standalone_table=False,
        ),
        VectorDomain.POLICY: DomainVectorConfig(
            table_name="policy",
            embedding_model=embedding_model,
            embed_dim=embed_dim,
            standalone_table=False,
        ),
        VectorDomain.CONTEST: DomainVectorConfig(
            table_name="contest",
            embedding_model=embedding_model,
            embed_dim=embed_dim,
            standalone_table=False,
        ),
    }


def build_hnsw_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "hnsw_m": settings.vector_hnsw_m,
        "hnsw_ef_construction": settings.vector_hnsw_ef_construction,
        "hnsw_ef_search": settings.vector_hnsw_ef_search,
        "hnsw_dist_method": settings.vector_hnsw_dist_method,
    }
