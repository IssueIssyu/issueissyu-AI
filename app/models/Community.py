from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column

from app.models.BaseEntity import BaseEntity


class Community(BaseEntity):
    __tablename__ = "community"

    community_id: Mapped[int] = mapped_column(
        "community_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    pin_id: Mapped[int | None] = mapped_column(
        "pin_id",
        BigInteger,
        ForeignKey("pin.pin_id"),
        nullable=True,
    )
