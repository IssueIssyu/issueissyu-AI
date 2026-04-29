from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.Pin import Pin


class PinImage(Base):
    __tablename__ = "pin_image"

    pin_image_id: Mapped[int] = mapped_column(
        "pin_image_id",
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
    pin: Mapped[Pin] = relationship(
        "Pin",
        foreign_keys=[pin_id],
        back_populates="pin_images",
        lazy="selectin",
    )
    pin_s3_key: Mapped[str] = mapped_column("pin_s3_key", String(500), nullable=False)
    pin_s3_url: Mapped[str] = mapped_column("pin_s3_url", String(500), nullable=False)
