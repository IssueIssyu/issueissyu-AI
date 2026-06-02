from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.config import Settings


class VectorDomain(str, Enum):
    COMPLAINT = "complaint"


@dataclass(frozen=True, slots=True)
class DomainVectorConfig:
    table_name: str
    embedding_model: str
    embed_dim: int
    # True면 table_name을 pgvector 테이블 전체명으로 사용(complaint_chunks_ 접두사 없음)
    standalone_table: bool = False


def build_vector_domain_configs(settings: Settings) -> dict[VectorDomain, DomainVectorConfig]:
    # Settings->VectorStoreService 도메인별 테이블, 임베딩 설정
    return {
        VectorDomain.COMPLAINT: DomainVectorConfig(
            table_name="complaint",
            embedding_model=settings.gemini_embedding_model,
            embed_dim=settings.vector_embed_dim,
            standalone_table=False,
        ),
    }
