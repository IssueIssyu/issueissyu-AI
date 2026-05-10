from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.PinLocation import PinLocation
    from app.models.User import User


class Location(Base):
    __tablename__ = "location"

    location_id: Mapped[int] = mapped_column(
        "location_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    region: Mapped[str] = mapped_column(
        "location",
        String(50),
        nullable=False,
    )
    adm_code: Mapped[str] = mapped_column("adm_code", String(10), nullable=False)

    users: Mapped[list[User]] = relationship(
        "User",
        back_populates="location",
        foreign_keys="User.location_id",
        lazy="selectin",
    )
    pin_locations: Mapped[list[PinLocation]] = relationship(
        "PinLocation",
        back_populates="location",
        foreign_keys="PinLocation.location_id",
        lazy="selectin",
    )
