from __future__ import annotations

from fastapi import UploadFile

from app.schemas.ImageExifGeoExtractResponseDTO import ImageExifGeoExtractResponseDTO
from app.services.ImageMultipartGeoService import ImageMultipartGeoService
from app.services.LocationResolveClient import LocationResolveClient


class ImageExifLocationResolveService:
    """이미지 EXIF 좌표 추출 후 코어 `/api/location/resolve`로 `location_id`·주소를 붙입니다."""

    def __init__(
        self,
        multipart_geo: ImageMultipartGeoService,
        location_resolve: LocationResolveClient,
    ) -> None:
        self._multipart_geo = multipart_geo
        self._location_resolve = location_resolve

    async def extract_and_resolve(self, file: UploadFile) -> ImageExifGeoExtractResponseDTO:
        point = await self._multipart_geo.extract_point_from_upload(file)
        if point is None:
            return ImageExifGeoExtractResponseDTO(point=None, location_id=None, address=None)

        resolved = await self._location_resolve.resolve_wgs84(
            latitude=point.latitude,
            longitude=point.longitude,
        )
        if resolved is None:
            return ImageExifGeoExtractResponseDTO(point=point, location_id=None, address=None)

        return ImageExifGeoExtractResponseDTO(
            point=point,
            location_id=resolved.location_id,
            address=resolved.address,
        )
