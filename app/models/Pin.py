from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, Identity, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.enum.PinType import PinType
from app.models.enum.ToneType import ToneType

if TYPE_CHECKING:
    from app.models.EventPin import EventPin
    from app.models.IssuePin import IssuePin
    from app.models.PinImage import PinImage
    from app.models.PinLocation import PinLocation
    from app.models.User import User


class Pin(BaseEntity):
    __tablename__ = "pin"

    pin_id: Mapped[int] = mapped_column(
        "pin_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    uid: Mapped[str] = mapped_column(
        "uid",
        String(36),
        ForeignKey("user.uid"),
        nullable=False,
    )
    pin_type: Mapped[PinType] = mapped_column(
        "pin_type",
        Enum(PinType, native_enum=False, length=32),
        nullable=False,
    )
    pin_title: Mapped[str] = mapped_column("pin_title", String(100), nullable=False)
    pin_content: Mapped[str] = mapped_column("pin_content", Text, nullable=False)
    tone_type: Mapped[ToneType] = mapped_column(
        "tone_type",
        Enum(ToneType, native_enum=False, length=32),
        nullable=False,
        default=ToneType.NONE,
        server_default=text("'없음'"),
    )
    like_count: Mapped[int] = mapped_column(
        "like_count",
        Integer,
        default=0,
        nullable=False,
        server_default=text("0"),
    )

    user: Mapped[User] = relationship(
        "User",
        back_populates="pins",
        foreign_keys=[uid],
        lazy="selectin",
    )
    pin_images: Mapped[list[PinImage]] = relationship(
        "PinImage",
        back_populates="pin",
        lazy="selectin",
    )
    event_pin: Mapped[EventPin | None] = relationship(
        "EventPin",
        back_populates="pin",
        uselist=False,
        lazy="selectin",
    )
    issue_pin: Mapped[IssuePin | None] = relationship(
        "IssuePin",
        back_populates="pin",
        uselist=False,
        lazy="selectin",
    )
    pin_location: Mapped[PinLocation | None] = relationship(
        "PinLocation",
        back_populates="pin",
        uselist=False,
        lazy="selectin",
    )
