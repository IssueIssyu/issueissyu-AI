from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, Enum, ForeignKey, Identity, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.SocialType import SocialType
from app.models.User import User


class OAuth(BaseEntity):
    __tablename__ = "oauth"

    auth_id: Mapped[int] = mapped_column(
        "auth_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        "uid",
        PGUUID(as_uuid=True),
        ForeignKey("user.uid"),
        nullable=False,
    )
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="oauths",
        lazy="selectin",
    )
    provider_id: Mapped[str] = mapped_column("provider_id", String(255), nullable=False)
    social_type: Mapped[SocialType] = mapped_column(
        "social_type",
        Enum(SocialType, native_enum=False, length=32),
        nullable=False,
    )
