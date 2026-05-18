from __future__ import annotations

from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement
from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.Pin import Pin

if TYPE_CHECKING:
    from app.models.Location import Location


class PinLocation(BaseEntity):
    """핀별 지역(행정) 및 좌표. pin_id당 최대 한 행.

    pin_point는 DB `geometry(Point,4326)` (WGS84)—Spring `columnDefinition`·네이버 지도 API와 동일 SRID.
    """

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
    detail_address: Mapped[str] = mapped_column(
        "detail_address",
        String(150),
        nullable=False,
    )
    pin_point: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )

    pin: Mapped[Pin] = relationship(
        "Pin",
        back_populates="pin_location",
        foreign_keys=[pin_id],
        lazy="selectin",
    )
    location: Mapped[Location] = relationship(
        "Location",
        back_populates="pin_locations",
        foreign_keys=[location_id],
        lazy="selectin",
    )
