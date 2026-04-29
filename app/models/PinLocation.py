from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.Location import Location
from app.models.PgPointType import PGPointType
from app.models.Pin import Pin


class PinLocation(BaseEntity):
    __tablename__ = "pin_location"

    pin_location_id: Mapped[int] = mapped_column(
        "pin_location_id",
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
    location_id: Mapped[int] = mapped_column(
        "location_id",
        BigInteger,
        ForeignKey("location.location_id"),
        nullable=False,
    )
    pin: Mapped[Pin] = relationship(
        "Pin",
        foreign_keys=[pin_id],
        back_populates="pin_locations",
        lazy="selectin",
    )
    location: Mapped[Location] = relationship(
        "Location",
        foreign_keys=[location_id],
        back_populates="pin_locations",
        lazy="selectin",
    )
    pin_point: Mapped[tuple[float, float]] = mapped_column(
        "pin_point",
        PGPointType(),
        nullable=False,
    )
    detail_address: Mapped[str] = mapped_column("detail_address", String(150), nullable=False)
