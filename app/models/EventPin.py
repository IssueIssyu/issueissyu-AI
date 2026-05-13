from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.Pin import Pin


class EventPin(BaseEntity):
    __tablename__ = "event_pin"

    event_pin_id: Mapped[int] = mapped_column(
        "event_pin_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    pin_id: Mapped[int] = mapped_column(
        "pin_id",
        BigInteger,
        ForeignKey("pin.pin_id"),
        nullable=False,
        unique=True,
    )
    pin: Mapped[Pin] = relationship(
        "Pin",
        foreign_keys=[pin_id],
        back_populates="event_pin",
        lazy="selectin",
    )
    event_start_time: Mapped[datetime] = mapped_column("event_start_time", DateTime, nullable=False)
    event_end_time: Mapped[datetime] = mapped_column("event_end_time", DateTime, nullable=False)
    discount: Mapped[str | None] = mapped_column("discount", String(255), nullable=True)
