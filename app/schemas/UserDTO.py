from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    user_name: str
    phone: str | None = None
    nickname: str | None = None
    email: str | None = None
    location_id: int | None = None
    event_alarm_active: bool
    hot_alarm_active: bool
    store_alarm_active: bool
    like_alarm_active: bool
    created_at: datetime
    updated_at: datetime | None = None
