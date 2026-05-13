"""AWS/RDS 연결 확인용 테이블 모델.

CREATE TABLE test(
    id BIGINT PRIMARY KEY,
    message TEXT
);
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DbConnectionCheck(Base):
    __tablename__ = "test"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
