from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.Wgs84PointDTO import Wgs84PointDTO


class ImageExifGeoExtractResponseDTO(BaseModel):
    """멀티파트 EXIF 좌표 + 코어(location/resolve)로 조회한 `location_id`·주소."""

    model_config = ConfigDict(frozen=True)

    point: Wgs84PointDTO | None = Field(
        default=None,
        description="GPS EXIF가 있으면 WGS84(EPSG:4326) 위·경도, 없으면 null.",
    )
    location_id: int | None = Field(
        default=None,
        description="LOCATION_CORE_BASE_URL 코어 `/api/location/resolve` 성공 시 행정 `location_id`.",
    )
    address: str | None = Field(
        default=None,
        description="코어에서 내려준 주소 문자열(GPS 또는 해석 실패 시 null).",
    )
