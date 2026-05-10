from __future__ import annotations

from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.Pin import Pin

if TYPE_CHECKING:
    from app.models.Location import Location


class PinLocation(Base):
    """핀별 지역(행정) 및 좌표. pin_id당 최대 한 행.

    pin_point는 DB `geometry(Point,4326)` (WGS84)—Spring `columnDefinition`·네이버 지도 API와 동일 SRID.
    """

    __tablename__ = "pin_location"

    pin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pin.pin_id"),
        primary_key=True,
    )
    location_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("location.location_id"),
        nullable=True,
    )
    pin_point: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )

    pin: Mapped[Pin] = relationship(
        "Pin",
        back_populates="pin_location",
        foreign_keys=[pin_id],
        lazy="selectin",
    )
    location: Mapped[Location | None] = relationship(
        "Location",
        back_populates="pin_locations",
        foreign_keys=[location_id],
        lazy="selectin",
    )
