from __future__ import annotations

from fastapi import UploadFile

from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.IssueDTO import CreateIssuePinRequest, ImageWithLocation, IssueAnalysisResult
from app.services.CoordinateResolveService import CoordinateResolveService
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
        coordinate_resolve_service: CoordinateResolveService,
        pin_repo: PinRepo,
        issue_pin_repo: IssuePinRepo,
        user_repo: UserRepo,
    ) -> None:
        self._vector_store_service = vector_store_service
        self._vlm_service = vlm_service
        self._image_exif_location_resolve_service = image_exif_location_resolve_service
        self._coordinate_resolve_service = coordinate_resolve_service
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
        user_content = f"title:{request.title}\n" + f"content: {request.content}\n"
        user_imgs = await self._extract_locations_from_images(images)
        user_location = await self._coordinate_resolve_service.resolve(latitude=request.latitude, longitude=request.longitude)
        user_address = user_location.address

        vlm_result = await self._vlm_service.analyze_image(user_text=user_content, images=user_imgs, user_location = user_address)

        query = vlm_result.get("retrieval_query") or user_content
        rag_result = await self._vector_store_service.aretrieve(query)







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
