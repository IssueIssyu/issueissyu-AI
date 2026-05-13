from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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
