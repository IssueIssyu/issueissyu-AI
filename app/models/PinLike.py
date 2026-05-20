from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.BaseEntity import BaseEntity


class PinLike(BaseEntity):
    __tablename__ = "pin_like"

    pin_like_id: Mapped[int] = mapped_column(
        "pin_like_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    pin_id: Mapped[int] = mapped_column(
        "pin_id",
        BigInteger,
        ForeignKey("pin.pin_id"),
        nullable=False,
    )
    uid: Mapped[str] = mapped_column(
        "uid",
        String(36),
        ForeignKey("user.uid"),
        nullable=False,
    )
