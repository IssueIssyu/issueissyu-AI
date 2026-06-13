from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.Community import Community


class CardnewsImageS3(Base):
    __tablename__ = "cardnews_image_s3"

    cardnews_image_s3_id: Mapped[int] = mapped_column(
        "cardnews_image_s3_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    community_id: Mapped[int] = mapped_column(
        "community_id",
        BigInteger,
        ForeignKey("community.community_id"),
        nullable=False,
    )
    community: Mapped[Community] = relationship(
        "Community",
        foreign_keys=[community_id],
        back_populates="cardnews_images",
        lazy="selectin",
    )
    cardnews_image_s3_key: Mapped[str] = mapped_column(
        "cardnews_image_s3_key",
        String(500),
        nullable=False,
    )
    cardnews_image_s3_url: Mapped[str] = mapped_column(
        "cardnews_image_s3_url",
        String(500),
        nullable=False,
    )
