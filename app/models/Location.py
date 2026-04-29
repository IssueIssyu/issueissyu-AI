from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enum.RegionCode import RegionCode

if TYPE_CHECKING:
    from app.models.PinLocation import PinLocation
    from app.models.UserLocation import UserLocation


class Location(Base):
    __tablename__ = "location"

    location_id: Mapped[int] = mapped_column(
        "location_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    region: Mapped[RegionCode] = mapped_column(
        "location",
        Enum(RegionCode, native_enum=False, length=64),
        nullable=False,
    )
    adm_code: Mapped[str] = mapped_column("adm_code", String(5), nullable=False)

    pin_locations: Mapped[list[PinLocation]] = relationship(
        "PinLocation",
        back_populates="location",
        lazy="selectin",
    )
    user_locations: Mapped[list[UserLocation]] = relationship(
        "UserLocation",
        back_populates="location",
        lazy="selectin",
    )
