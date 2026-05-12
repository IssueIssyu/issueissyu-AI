from __future__ import annotations

from app.schemas.LocationResolveDTO import LocationResolveResultDTO
from app.services.LocationResolveClient import LocationResolveClient


class CoordinateResolveService:
    """위·경도 좌표를 코어 `/api/location/resolve`로 보내 `location_id`·주소를 반환합니다."""

    def __init__(self, location_resolve: LocationResolveClient) -> None:
        self._location_resolve = location_resolve

    async def resolve(
        self,
        latitude: float,
        longitude: float,
    ) -> LocationResolveResultDTO | None:
        return await self._location_resolve.resolve_wgs84(latitude, longitude)
