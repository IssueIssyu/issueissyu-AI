from __future__ import annotations

from fastapi import UploadFile

from app.models.enum.ToneType import ToneType
from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.IssueDTO import IssueAnalysisResult
from app.schemas.ImageExifGeoExtractResponseDTO import ImageExifGeoExtractResponseDTO
from app.services.ImageExifLocationResolveService import ImageExifLocationResolveService
from app.services.VLMService import VLMService
from app.services.VectorStoreService import VectorStoreService

MAX_IMAGES = 5


class IssueService:
    def __init__(
        self,
        vector_store_service: VectorStoreService,
        vlm_service: VLMService,
        image_exif_location_resolve_service: ImageExifLocationResolveService,
        pin_repo: PinRepo,
        issue_pin_repo: IssuePinRepo,
        user_repo: UserRepo,
    ) -> None:
        self._vector_store_service = vector_store_service
        self._vlm_service = vlm_service
        self._image_exif_location_resolve_service = image_exif_location_resolve_service
        self._pin_repo = pin_repo
        self._issue_pin_repo = issue_pin_repo
        self._user_repo = user_repo

    async def create_issue_pin(
        self,
        *,
        uid: str,
        images: list[UploadFile],
        title: str,
        content: str,
        tone: ToneType,
        latitude: float,
        longitude: float,
    ) -> IssueAnalysisResult:
        ...

    async def _extract_locations_from_images(
        self,
        images: list[UploadFile],
    ) -> list[ImageExifGeoExtractResponseDTO]:
        results: list[ImageExifGeoExtractResponseDTO] = []
        for image in images[:MAX_IMAGES]:
            resolved = await self._image_exif_location_resolve_service.extract_and_resolve(image)
            results.append(resolved)
        return results
