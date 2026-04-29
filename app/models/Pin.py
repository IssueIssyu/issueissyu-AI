from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Enum, Identity, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.enum.PinType import PinType
from app.models.enum.ToneType import ToneType

if TYPE_CHECKING:
    from app.models.EventPin import EventPin
    from app.models.PinImage import PinImage
    from app.models.PinLocation import PinLocation


class Pin(BaseEntity):
    __tablename__ = "pin"

    pin_id: Mapped[int] = mapped_column(
        "pin_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    pin_type: Mapped[PinType] = mapped_column(
        "pin_type",
        Enum(PinType, native_enum=False, length=32),
        nullable=False,
    )
    pin_title: Mapped[str] = mapped_column("pin_title", String(100), nullable=False)
    pin_content: Mapped[str] = mapped_column("pin_content", Text, nullable=False)
    tone_type: Mapped[ToneType | None] = mapped_column(
        "tone_type",
        Enum(ToneType, native_enum=False, length=32),
        nullable=True,
    )
    visibility_status: Mapped[bool] = mapped_column(
        "visibility_status",
        Boolean,
        default=True,
        nullable=False,
    )
    pin_images: Mapped[list[PinImage]] = relationship(
        "PinImage",
        back_populates="pin",
        lazy="selectin",
    )
    pin_locations: Mapped[list[PinLocation]] = relationship(
        "PinLocation",
        back_populates="pin",
        lazy="selectin",
    )
    event_pin: Mapped[EventPin | None] = relationship(
        "EventPin",
        back_populates="pin",
        uselist=False,
        lazy="selectin",
    )