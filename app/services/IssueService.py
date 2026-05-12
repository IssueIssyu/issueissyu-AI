from __future__ import annotations

from fastapi import UploadFile

from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.IssueDTO import CreateIssuePinRequest, ImageWithLocation, IssueAnalysisResult
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
        request: CreateIssuePinRequest,
    ) -> IssueAnalysisResult:
        vlm_result = await self._vlm_service.analyze_image()
        vector_result= await self._vector_store_service.aretrieve()

    async def _extract_locations_from_images(
        self,
        images: list[UploadFile],
    ) -> list[ImageWithLocation]:
        results: list[ImageWithLocation] = []
        for image in images[:MAX_IMAGES]:
            resolved = await self._image_exif_location_resolve_service.extract_and_resolve(image)
            await image.seek(0)
            results.append(ImageWithLocation(image=image, address=resolved.address))
        return results
