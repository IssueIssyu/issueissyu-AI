from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LocationResolveResultDTO(BaseModel):
    """코어 `GET /api/location/resolve` 응답의 `result` 페이로드."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    location_id: int = Field(alias="locationId")
    address: str
