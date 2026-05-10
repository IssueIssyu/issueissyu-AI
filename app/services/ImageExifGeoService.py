from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image
from PIL.ExifTags import GPSTAGS, IFD

from app.schemas.Wgs84PointDTO import Wgs84PointDTO


class ImageExifGeoService:
    """이미지 바이너리에서 EXIF GPS를 읽어 WGS84(EPSG:4326) 십진 도 좌표로 반환."""

    @staticmethod
    def extract_wgs84_point(image_bytes: bytes) -> Wgs84PointDTO | None:
        if not image_bytes:
            return None
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                exif = img.getexif()
                if not exif:
                    return None
                gps_raw = exif.get_ifd(IFD.GPS)
        except Exception:
            return None
        if not gps_raw:
            return None

        gps: dict[str, Any] = {GPSTAGS.get(t, str(t)): v for t, v in gps_raw.items()}

        lat_vals = gps.get("GPSLatitude")
        lon_vals = gps.get("GPSLongitude")
        lat_ref = gps.get("GPSLatitudeRef")
        lon_ref = gps.get("GPSLongitudeRef")
        if not lat_vals or not lon_vals:
            return None
        if lat_ref not in ("N", "S") or lon_ref not in ("E", "W"):
            return None

        lat = ImageExifGeoService._coords_to_decimal(lat_vals, lat_ref == "S")
        lon = ImageExifGeoService._coords_to_decimal(lon_vals, lon_ref == "W")

        try:
            return Wgs84PointDTO(latitude=lat, longitude=lon)
        except ValueError:
            return None

    @staticmethod
    def _coords_to_decimal(parts: tuple[Any, ...], negate: bool) -> float:
        deg, mins, secs = parts
        value = (
            ImageExifGeoService._ratio_to_float(deg)
            + ImageExifGeoService._ratio_to_float(mins) / 60.0
            + ImageExifGeoService._ratio_to_float(secs) / 3600.0
        )
        return -value if negate else value

    @staticmethod
    def _ratio_to_float(value: Any) -> float:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            denom = getattr(value, "denominator") or 1
            return float(getattr(value, "numerator")) / float(denom)
        return float(value)
