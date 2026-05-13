from __future__ import annotations

import logging
from typing import Any

from fastapi import UploadFile
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters

from app.core.codes import ErrorCode
from app.core.exceptions import raise_business_exception
from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.IssueDTO import (
    CreateIssuePinRequest,
    ImageWithLocation,
    IssueAnalysisResult,
    ReliabilityBasis,
)
from app.services.ImageExifLocationResolveService import ImageExifLocationResolveService
from app.services.issue_pin_prompt import build_issue_pin_prompt_from_pipeline_bundle
from app.services.IssuePinLLMService import IssuePinLLMService
from app.services.vector_domains import VectorDomain
from app.services.VLMService import VLMService
from app.services.VectorStoreService import VectorStoreService

MAX_IMAGES = 5
logger = logging.getLogger(__name__)


class IssueService:
    def __init__(
        self,
        vector_store_service: VectorStoreService,
        vlm_service: VLMService,
        image_exif_location_resolve_service: ImageExifLocationResolveService,
        issue_pin_llm_service: IssuePinLLMService,
        pin_repo: PinRepo,
        issue_pin_repo: IssuePinRepo,
        user_repo: UserRepo,
    ) -> None:
        self._vector_store_service = vector_store_service
        self._vlm_service = vlm_service
        self._image_exif_location_resolve_service = image_exif_location_resolve_service
        self._issue_pin_llm_service = issue_pin_llm_service
        self._pin_repo = pin_repo
        self._issue_pin_repo = issue_pin_repo
        self._user_repo = user_repo

    @staticmethod
    def _user_content_from_request(request: CreateIssuePinRequest) -> str:
        return f"title:{request.title.strip()}\ncontent:{request.content.strip()}\n"

    @staticmethod
    def _user_location_from_request(request: CreateIssuePinRequest) -> str | None:
        return f"{request.latitude:.6f},{request.longitude:.6f}"

    @staticmethod
    def _build_rag_metadata_filters(vlm_result: dict[str, Any]) -> MetadataFilters | None:
        raw = vlm_result.get("category")
        if not isinstance(raw, dict):
            return None
        domain_name = raw.get("domain")
        if not isinstance(domain_name, str):
            return None
        d = domain_name.strip()
        if not d or d == "공통":
            return None
        return MetadataFilters(
            filters=[MetadataFilter(key="category", value=d)]
        )

    @staticmethod
    def _rag_hits_to_dicts(hits: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for hit in hits:
            node = hit.node
            meta = node.metadata if node.metadata is not None else {}
            rows.append(
                {
                    "text": node.get_content(),
                    "score": hit.score,
                    "metadata": dict(meta) if hasattr(meta, "items") else {},
                }
            )
        return rows

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    @staticmethod
    def _reliability_from_vlm(vlm_result: dict[str, Any]) -> float:
        raw = vlm_result.get("confidence_score")
        try:
            score = float(raw)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, score))

    @staticmethod
    def _reliability_basis_from_vlm(vlm_result: dict[str, Any]) -> ReliabilityBasis:
        location_status: str | None = None
        location_message: str | None = None
        location_verification = vlm_result.get("location_verification")
        if isinstance(location_verification, dict):
            location_status = IssueService._optional_text(location_verification.get("status"))
            location_message = IssueService._optional_text(location_verification.get("message"))

        raw_validity = vlm_result.get("validity")
        validity = raw_validity if isinstance(raw_validity, bool) else False

        return ReliabilityBasis(
            confidence_score=IssueService._reliability_from_vlm(vlm_result),
            validity=validity,
            location_verification_status=location_status,
            location_verification_message=location_message,
            error_code=IssueService._optional_text(vlm_result.get("error_code")),
            risk_note=IssueService._optional_text(vlm_result.get("risk_note")),
            scene_summary=IssueService._optional_text(vlm_result.get("scene_summary")),
        )

    async def issue_pin_ai_make(
        self,
        *,
        uid: str,
        images: list[UploadFile],
        request: CreateIssuePinRequest,
    ) -> IssueAnalysisResult:

        if not images:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, detail="이미지는 1장 이상 필요합니다.")

        user_content = self._user_content_from_request(request)
        user_imgs = await self._extract_locations_from_images(images=images)
        user_location = self._user_location_from_request(request)

        vlm_result = await self._vlm_service.analyze_image(
            user_text=user_content,
            images=user_imgs,
            user_location=user_location,
        )

        query = (vlm_result.get("retrieval_query") or "").strip()
        if not query:
            query = user_content.strip()

        filters = self._build_rag_metadata_filters(vlm_result)
        logger.warning(
            "RAG retrieve start — query=%r, domain=%s, filters=%s",
            query, VectorDomain.COMPLAINT.value, filters,
        )
        rag_hits = await self._vector_store_service.aretrieve(
            query=query,
            domain=VectorDomain.COMPLAINT,
            similarity_top_k=10,
            filters=filters,
        )
        logger.warning("Issue RAG hits count=%d, hits=%s", len(rag_hits), rag_hits)
        rag_payload = self._rag_hits_to_dicts(rag_hits)

        bundle: dict[str, Any] = {
            "issue": {
                "title": request.title,
                "content": request.content,
                "tone": request.tone,
            },
            "vlm_result": vlm_result,
            "rag_query": query,
            "rag_filters_applied": filters is not None,
            "rag_hits": rag_payload,
        }
        pin_prompt = build_issue_pin_prompt_from_pipeline_bundle(bundle)
        pin_body = await self._issue_pin_llm_service.generate_pin_text(prompt=pin_prompt)

        for row in user_imgs:
            await row.image.seek(0)

        return IssueAnalysisResult(
            title=request.title,
            content=pin_body,
            reliability=self._reliability_from_vlm(vlm_result),
            reliability_basis=self._reliability_basis_from_vlm(vlm_result),
        )

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
