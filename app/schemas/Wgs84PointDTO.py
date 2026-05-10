from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Wgs84PointDTO(BaseModel):
    """WGS84 지리좌표(위·경도, 도 단위). PostGIS `geometry(Point,4326)`·EXIF GPS와 동일 체계."""

    model_config = ConfigDict(frozen=True)

    crs: Literal["EPSG:4326"] = Field(
        default="EPSG:4326",
        description="OGC 코드: 위도(lat)·경도(lon)는 WGS84 타원체 기준 도(°) 단위.",
    )
    latitude: float = Field(ge=-90, le=90, description="북쪽 양수(°).")
    longitude: float = Field(ge=-180, le=180, description="동쪽 양수(°).")

    @field_validator("latitude", "longitude")
    @classmethod
    def round_float(cls, v: float) -> float:
        # EXIF 유리수 반올림으로 생기는 미세 노이즈만 정리
        return round(v, 7)

    def to_wkt_point_xy(self) -> str:
        """OGC WKT Point. EPSG:4326에서 일반적으로 X=경도, Y=위도 (`geometry(Point,4326)` 삽입용)."""

        return f"POINT({self.longitude} {self.latitude})"
