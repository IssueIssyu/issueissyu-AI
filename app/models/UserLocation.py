from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.Location import Location
from app.models.User import User


class UserLocation(BaseEntity):
    __tablename__ = "user_location"

    user_location_id: Mapped[int] = mapped_column(
        "user_location_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    location_id: Mapped[int] = mapped_column(
        "location_id",
        BigInteger,
        ForeignKey("location.location_id"),
        nullable=False,
    )
    uid: Mapped[str] = mapped_column(
        "uid",
        String(36),
        ForeignKey("user.uid"),
        nullable=False,
    )
    location: Mapped[Location] = relationship(
        "Location",
        foreign_keys=[location_id],
        back_populates="user_locations",
        lazy="selectin",
    )
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[uid],
        back_populates="user_locations",
        lazy="selectin",
    )
