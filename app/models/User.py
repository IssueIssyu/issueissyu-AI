from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.BaseEntity import BaseEntity


class User(BaseEntity):
    __tablename__ = "user"

    uid: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4,)
    phone: Mapped[str | None] = mapped_column(String(13), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(15), nullable=True)
    #Todo - 유저 위치정보 데이터형식 확인하고 구현하기
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hot_alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    store_alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    like_alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
