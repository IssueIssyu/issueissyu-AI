from __future__ import annotations

from sqlalchemy import BigInteger, Float, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity


class Community(BaseEntity):
    __tablename__ = "community"

    community_id: Mapped[int] = mapped_column(
        "community_id",
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
    community_type: Mapped[str] = mapped_column("community_type", String(50), nullable=False)
    popularity: Mapped[float] = mapped_column("popularity", Float, nullable=False, default=0.0)
    cardnews_images: Mapped[list["CardnewsImageS3"]] = relationship(
        "CardnewsImageS3",
        back_populates="community",
        lazy="selectin",
    )
