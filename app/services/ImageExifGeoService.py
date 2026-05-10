from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from PIL import Image
from PIL.ExifTags import GPSTAGS, IFD

from app.schemas.Wgs84PointDTO import Wgs84PointDTO

logger = logging.getLogger(__name__)

# Pillow 12+: IFD.GPSInfo, 그 이전 버전 일부는 IFD.GPS. 존재하지 않으면 TIFF 표준값 34853(0x8825).
_GPS_IFD = getattr(IFD, "GPSInfo", None)
if _GPS_IFD is None:
    _GPS_IFD = getattr(IFD, "GPS", 34853)

# GPS 서브디렉토리 표준 로컬 태그 번호. GPSTAGS 매핑이 어긋난 파일도 읽기 위함.
_GPS_TAG_LAT_REF = 1
_GPS_TAG_LAT = 2
_GPS_TAG_LON_REF = 3
_GPS_TAG_LON = 4


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
                gps_raw = exif.get_ifd(_GPS_IFD)
        except Exception:
            return None
        if not gps_raw:
            return None

        gps_by_name: dict[str, Any] = {}
        for tag_id, val in gps_raw.items():
            name = GPSTAGS.get(tag_id)
            if name:
                gps_by_name[name] = val

        lat_vals = gps_by_name.get("GPSLatitude") or gps_raw.get(_GPS_TAG_LAT)
        lon_vals = gps_by_name.get("GPSLongitude") or gps_raw.get(_GPS_TAG_LON)
        lat_ref = gps_by_name.get("GPSLatitudeRef") or gps_raw.get(_GPS_TAG_LAT_REF)
        lon_ref = gps_by_name.get("GPSLongitudeRef") or gps_raw.get(_GPS_TAG_LON_REF)

        parts_lat = ImageExifGeoService._normalize_dms_triple(lat_vals)
        parts_lon = ImageExifGeoService._normalize_dms_triple(lon_vals)
        if parts_lat is None or parts_lon is None:
            return None

        lat_dir = ImageExifGeoService._normalize_latlon_ref(lat_ref, ("N", "S"))
        lon_dir = ImageExifGeoService._normalize_latlon_ref(lon_ref, ("E", "W"))
        # 방향 태그가 bytes(b'N')가 아닌 str로만 검사하던 문제·빈 태그 보정. 남·서반구는 제대로 된 ref 필요.
        if lat_dir is None:
            lat_dir = "N"
            logger.debug("GPSLatitudeRef 누락/비정상 — N으로 가정")
        if lon_dir is None:
            lon_dir = "E"
            logger.debug("GPSLongitudeRef 누락/비정상 — E로 가정")

        lat = ImageExifGeoService._coords_to_decimal(parts_lat, lat_dir == "S")
        lon = ImageExifGeoService._coords_to_decimal(parts_lon, lon_dir == "W")

        try:
            dto = Wgs84PointDTO(latitude=lat, longitude=lon)
        except ValueError:
            return None

        logger.info(
            "EXIF GPS 추출 완료 crs=%s latitude=%s longitude=%s (ref lat=%s lon=%s)",
            dto.crs,
            dto.latitude,
            dto.longitude,
            lat_dir,
            lon_dir,
        )
        return dto

    @staticmethod
    def _normalize_latlon_ref(raw: Any, allowed: tuple[str, str]) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            s = raw.decode("ascii", errors="ignore").strip("\x00 \t\n\r")
        else:
            s = str(raw).strip("\x00 \t\n\r")
        if not s:
            return None
        c = s[0].upper()
        if c in allowed:
            return c
        return None

    @staticmethod
    def _normalize_dms_triple(parts: Any) -> tuple[Any, Any, Any] | None:
        if parts is None:
            return None
        if not isinstance(parts, (list, tuple)):
            return None
        seq = list(parts)
        if len(seq) == 2:
            seq.append(0)
        if len(seq) != 3:
            return None
        return (seq[0], seq[1], seq[2])

    @staticmethod
    def _coords_to_decimal(parts: tuple[Any, Any, Any], negate: bool) -> float:
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
