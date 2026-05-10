from __future__ import annotations

from io import BytesIO

from fastapi import UploadFile
from PIL import Image

from app.core.codes import ErrorCode
from app.core.exceptions import raise_file_exception
from app.schemas.Wgs84PointDTO import Wgs84PointDTO
from app.services.ImageExifGeoService import ImageExifGeoService


class ImageMultipartGeoService:
    """`multipart/form-data`로 받은 이미지에서 EPSG:4326(WGS84) 좌표를 추출."""

    ALLOWED_MEDIA_TYPES: frozenset[str] = frozenset(
        {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/x-tiff"}
    )
    MAX_IMAGE_BYTES: int = 20 * 1024 * 1024

    async def extract_point_from_upload(self, file: UploadFile) -> Wgs84PointDTO | None:
        ctype = (file.content_type or "").split(";")[0].strip().lower()
        if ctype and ctype not in self.ALLOWED_MEDIA_TYPES and ctype != "application/octet-stream":
            raise_file_exception(
                ErrorCode.FILE_TYPE_NOT_SUPPORTED,
                detail="지원 형식: JPEG, PNG, WebP, TIFF 또는 application/octet-stream",
            )

        raw = await file.read(size=self.MAX_IMAGE_BYTES + 1)
        if len(raw) > self.MAX_IMAGE_BYTES:
            raise_file_exception(ErrorCode.FILE_SIZE_TOO_LARGE)
        if not raw:
            raise_file_exception(ErrorCode.FILE_UPLOAD_ERROR, detail="빈 파일입니다.")

        self._ensure_decodable_image(raw)
        return ImageExifGeoService.extract_wgs84_point(raw)

    @staticmethod
    def _ensure_decodable_image(data: bytes) -> None:
        try:
            with Image.open(BytesIO(data)) as img:
                img.load()
        except Exception:
            raise_file_exception(
                ErrorCode.FILE_TYPE_NOT_SUPPORTED,
                detail="이미지로 디코딩할 수 없습니다.",
            )
