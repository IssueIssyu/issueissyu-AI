from __future__ import annotations

from typing import TYPE_CHECKING

from uuid import uuid4

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.PgPointType import PGPointType

if TYPE_CHECKING:
    from app.models.OAuth import OAuth
    from app.models.UserLocation import UserLocation

class User(BaseEntity):
    __tablename__ = "user"

    uid: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid4().hex)
    phone: Mapped[str | None] = mapped_column(String(13), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(15), nullable=True)
    user_point: Mapped[tuple[float, float] | None] = mapped_column(PGPointType(), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hot_alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    store_alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    like_alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    oauths: Mapped[list[OAuth]] = relationship("OAuth", back_populates="user", lazy="selectin")
    user_locations: Mapped[list[UserLocation]] = relationship(
        "UserLocation",
        back_populates="user",
        lazy="selectin",
    )
