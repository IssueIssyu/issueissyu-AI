from __future__ import annotations

from sqlalchemy import BigInteger, Enum, ForeignKey, Identity, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.Pin import Pin
from app.models.enum.IssuePinState import IssuePinState


class IssuePin(BaseEntity):
    __tablename__ = "issue_pin"

    issue_pin_id: Mapped[int] = mapped_column(
        "issue_pin_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    issue_pin_state: Mapped[IssuePinState] = mapped_column(
        "issue_pin_state",
        Enum(IssuePinState, native_enum=False, length=255),
        nullable=False,
    )
    petition_count: Mapped[int] = mapped_column(
        "petition_count",
        Integer,
        nullable=False,
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
        back_populates="issue_pin",
        lazy="selectin",
    )
