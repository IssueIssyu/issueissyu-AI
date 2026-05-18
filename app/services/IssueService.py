from __future__ import annotations

import asyncio
import logging
import mimetypes
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, UploadFile

from app.core.config import settings
from app.core.codes import ErrorCode
from app.core.exceptions import raise_business_exception, raise_file_exception, raise_validation_exception
from app.models.IssuePin import IssuePin
from app.models.Pin import Pin
from app.models.PinImage import PinImage
from app.models.PinLocation import PinLocation
from app.models.enum.IssuePinState import IssuePinState
from app.models.enum.PinType import PinType
from app.repositories.CommunityRepo import CommunityRepo
from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.PinLikeRepo import PinLikeRepo
from app.repositories.PinImageRepo import PinImageRepo
from app.repositories.PinLocationRepo import PinLocationRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.utils.S3Util import S3Util
from app.schemas.IssueDTO import (
    CreateIssuePinRequest,
    ImageUploadStatus,
    IssueAnalysisResult,
    IssuePinHomeDetailResponse,
    IssuePinHomeImageItem,
    IssuePinReliabilityResponse,
    ReliabilityStatus,
)
from app.services.internal.issue_confidence_basis import is_failed_reliability_content
from app.schemas.issue_pin_job import ImageSnapshot, IssuePinReliabilityJob
from app.services.VectorStoreService import VectorStoreService
from app.services.internal.IssuePinBackgroundRunner import IssuePinBackgroundRunner
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.IssueRagPlannerService import IssueRagPlannerService
from app.services.internal.geo.LocationResolveClient import LocationResolveClient
from app.services.prompts import build_issue_pin_prompt_from_pipeline_bundle
from app.services.vector_domains import VectorDomain
from app.utils.geo import wkt_point_from_wgs84

logger = logging.getLogger(__name__)
SINGLE_RETRIEVAL_TOP_K = 5
S3_ISSUE_IMAGE_PREFIX = "issueimage"


class IssueService:
    def __init__(
        self,
        vector_store_service: VectorStoreService,
        issue_rag_planner_service: IssueRagPlannerService,
        location_resolve_client: LocationResolveClient,
        issue_pin_llm_service: IssuePinLLMService,
        pin_repo: PinRepo,
        issue_pin_repo: IssuePinRepo,
        pin_location_repo: PinLocationRepo,
        pin_image_repo: PinImageRepo,
        pin_like_repo: PinLikeRepo,
        community_repo: CommunityRepo,
        user_repo: UserRepo,
        s3_util: S3Util,
        background_runner: IssuePinBackgroundRunner,
    ) -> None:
        self._vector_store_service = vector_store_service
        self._issue_rag_planner_service = issue_rag_planner_service
        self._location_resolve_client = location_resolve_client
        self._issue_pin_llm_service = issue_pin_llm_service
        self._pin_repo = pin_repo
        self._issue_pin_repo = issue_pin_repo
        self._pin_location_repo = pin_location_repo
        self._pin_image_repo = pin_image_repo
        self._pin_like_repo = pin_like_repo
        self._s3_util = s3_util
        self._community_repo = community_repo
        self._user_repo = user_repo
        self._background_runner = background_runner

    @staticmethod
    def _format_pin_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        localized = value.astimezone(ZoneInfo("Asia/Seoul"))
        return localized.strftime("%Y-%m-%d %H:%M:%S.%f")

    @staticmethod
    def _is_pin_updated(*, created_at: datetime, updated_at: datetime | None) -> bool:
        if updated_at is None:
            return False
        return updated_at > created_at

    @staticmethod
    def _user_coordinates_from_request(request: CreateIssuePinRequest) -> str:
        return f"{request.latitude:.6f},{request.longitude:.6f}"

    async def _resolve_user_location_address(self, request: CreateIssuePinRequest) -> str | None:
        resolved = await self._location_resolve_client.resolve_wgs84(
            latitude=request.latitude,
            longitude=request.longitude,
        )
        if resolved is None:
            return None
        address = (resolved.address or "").strip()
        return address or None

    @staticmethod
    def _rag_hits_to_dicts(hits: list[Any]) -> list[dict[str, Any]]:
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
    def _sanitize_single_query(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 180:
            text = text[:180].rstrip()
        return text

    @staticmethod
    def _tune_title(*, original_title: str, rewritten: dict[str, Any]) -> str:
        primary = rewritten.get("primary_query")
        keyword = rewritten.get("keyword_query")
        candidate = (
            IssueService._sanitize_single_query(primary)
            or IssueService._sanitize_single_query(keyword)
            or original_title.strip()
        )
        # 제목은 짧고 선명하게: 불필요한 접미 구두점 제거 + 길이 제한
        tuned = candidate.strip().rstrip(" .,!?:;")
        if len(tuned) > 42:
            tuned = tuned[:42].rstrip()
        return tuned or "민원 제보"

    async def issue_pin_ai_make(
        self,
        *,
        uid: str,
        request: CreateIssuePinRequest,
    ) -> IssueAnalysisResult:
        _ = uid
        safe_title = request.title.strip()
        safe_content = request.content.strip()
        user_content = f"title:{safe_title}\ncontent:{safe_content}\n".strip()
        user_location = await self._resolve_user_location_address(request)
        if user_location is None:
            user_location = "주소 확인 불가"
        user_coordinates = self._user_coordinates_from_request(request)

        rewritten = await self._issue_rag_planner_service.rewrite_queries(
            title=safe_title,
            content=safe_content,
            user_location=user_coordinates,
        )
        filters = None
        primary_query = self._sanitize_single_query(rewritten.get("primary_query"))
        keyword_query = self._sanitize_single_query(rewritten.get("keyword_query"))
        selected_query = primary_query or keyword_query or user_content
        logger.warning(
            "Issue RAG retrieve start — single_query=%r source=%s domain=%s filters=%s top_k=%d",
            selected_query,
            "primary" if primary_query else ("keyword" if keyword_query else "fallback"),
            VectorDomain.COMPLAINT.value,
            filters,
            SINGLE_RETRIEVAL_TOP_K,
        )

        rag_hits = await self._vector_store_service.aretrieve(
            query=selected_query,
            domain=VectorDomain.COMPLAINT,
            similarity_top_k=SINGLE_RETRIEVAL_TOP_K,
            filters=filters,
        )
        if len(rag_hits) > SINGLE_RETRIEVAL_TOP_K:
            logger.warning(
                "Issue RAG capped hits: raw=%d capped=%d",
                len(rag_hits),
                SINGLE_RETRIEVAL_TOP_K,
            )
            rag_hits = rag_hits[:SINGLE_RETRIEVAL_TOP_K]
        rag_payload = self._rag_hits_to_dicts(rag_hits)
        logger.warning("Issue RAG hits=%d", len(rag_hits))

        bundle: dict[str, Any] = {
            "issue": {
                "title": safe_title,
                "content": safe_content,
                "tone": request.tone,
                "location": user_location,
            },
            "rag_queries": [selected_query],
            "rag_filters_applied": filters is not None,
            "rag_hits": rag_payload,
        }
        pin_prompt = build_issue_pin_prompt_from_pipeline_bundle(bundle)
        pin_body = await self._issue_pin_llm_service.generate_pin_text(prompt=pin_prompt)
        tuned_title = self._tune_title(
            original_title=request.title,
            rewritten=rewritten,
        )

        return IssueAnalysisResult(
            title=tuned_title,
            content=pin_body,
        )

    @staticmethod
    def _validate_create_issue_pin_payload(
        *,
        title: str,
        content: str,
        images: list[UploadFile],
    ) -> tuple[str, str]:
        safe_title = title.strip()
        safe_content = content.strip()
        if not safe_title:
            raise_validation_exception(ErrorCode.VALIDATION_ERROR, detail="제목을 입력해 주세요.")
        if not safe_content:
            raise_validation_exception(ErrorCode.VALIDATION_ERROR, detail="본문을 입력해 주세요.")
        if len(safe_title) > settings.pin_title_max_length:
            raise_validation_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"제목은 {settings.pin_title_max_length}자 이하여야 합니다.",
            )
        if len(safe_content) > settings.pin_content_max_length:
            raise_validation_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"본문은 {settings.pin_content_max_length}자 이하여야 합니다.",
            )
        if len(images) > settings.issue_pin_max_images:
            raise_validation_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"이미지는 최대 {settings.issue_pin_max_images}장까지 업로드할 수 있습니다.",
            )
        return safe_title, safe_content

    @staticmethod
    async def _snapshot_upload_images(images: list[UploadFile]) -> tuple[ImageSnapshot, ...]:
        snapshots: list[ImageSnapshot] = []
        for index, upload in enumerate(images, start=1):
            raw = await upload.read()
            if not raw:
                raise_validation_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"이미지 파일이 비어 있습니다. (index={index})",
                )
            mime = (upload.content_type or "").split(";")[0].strip().lower()
            if not mime:
                guessed, _ = mimetypes.guess_type(upload.filename or "")
                mime = (guessed or "").split(";")[0].strip().lower()
            if not mime.startswith("image/"):
                raise_file_exception(ErrorCode.FILE_TYPE_NOT_SUPPORTED)
            name = upload.filename or f"image_{index}.jpg"
            snapshots.append(
                ImageSnapshot(data=raw, content_type=mime, filename=name),
            )
        return tuple(snapshots)

    async def _upload_snapshot_to_s3(self, snap: ImageSnapshot) -> dict[str, str]:
        return await self._s3_util.upload_bytes(
            snap.data,
            filename=snap.filename,
            content_type=snap.content_type,
            prefix=S3_ISSUE_IMAGE_PREFIX,
        )

    async def _upload_pin_images_sync(
        self,
        *,
        pin_id: int,
        snapshots: tuple[ImageSnapshot, ...],
    ) -> list[PinImage]:
        """S3 업로드는 병렬(asyncio.gather), DB 저장은 동일 세션에서 순차 처리."""
        if not snapshots:
            return []

        try:
            uploaded_list = await asyncio.gather(
                *[self._upload_snapshot_to_s3(snap) for snap in snapshots],
            )
        except Exception:
            logger.exception("issue pin image S3 upload failed pin_id=%s", pin_id)
            raise_file_exception(ErrorCode.FILE_UPLOAD_ERROR)

        saved: list[PinImage] = []
        for index, (snap, uploaded) in enumerate(zip(snapshots, uploaded_list, strict=True)):
            pin_image = PinImage(
                pin_id=pin_id,
                pin_s3_key=uploaded["key"],
                pin_s3_url=uploaded["url"],
                is_main=index == 0,
            )
            await self._pin_image_repo.save(pin_image, flush_immediately=True)
            saved.append(pin_image)
        return saved

    async def create_issue_pin(
        self,
        *,
        uid: str,
        request: CreateIssuePinRequest,
        images: list[UploadFile] | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> IssuePinHomeDetailResponse:
        uploads = images or []
        safe_title, safe_content = self._validate_create_issue_pin_payload(
            title=request.title,
            content=request.content,
            images=uploads,
        )
        user = await self._user_repo.get_by_uid(uid)
        if user is None:
            raise_validation_exception(ErrorCode.USER_NOT_FOUND)

        resolved = await self._location_resolve_client.resolve_wgs84(
            latitude=request.latitude,
            longitude=request.longitude,
        )
        if resolved is None:
            raise_validation_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="위치를 확인할 수 없습니다. 좌표를 다시 확인해 주세요.",
            )
        detail_address = resolved.address.strip()
        if not detail_address:
            raise_validation_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="위치 주소를 확인할 수 없습니다.",
            )
        detail_address = detail_address[:150]
        location_id = resolved.location_id
        user_address = detail_address

        image_snapshots = await self._snapshot_upload_images(uploads)
        user_gps = self._user_coordinates_from_request(request)

        pin = Pin(
            uid=uid,
            pin_type=PinType.ISSUE,
            pin_title=safe_title,
            pin_content=safe_content,
            tone_type=request.tone,
            like_count=0,
            view_count=0,
        )
        await self._pin_repo.save(pin, flush_immediately=True)

        issue_pin = IssuePin(
            issue_pin_state=IssuePinState.BEFORE_PROGRESS,
            petition_count=0,
            pin_id=pin.pin_id,
            issue_confidence=None,
            confidence_content=None,
        )
        await self._issue_pin_repo.save(issue_pin, flush_immediately=True)

        pin_location = PinLocation(
            pin_id=pin.pin_id,
            location_id=location_id,
            detail_address=detail_address,
            pin_point=wkt_point_from_wgs84(
                latitude=request.latitude,
                longitude=request.longitude,
            ),
        )
        await self._pin_location_repo.save(pin_location, flush_immediately=True)

        saved_images: list[PinImage] = []
        if image_snapshots:
            saved_images = await self._upload_pin_images_sync(
                pin_id=pin.pin_id,
                snapshots=image_snapshots,
            )

        await self._pin_repo.commit()

        self._background_runner.schedule(
            IssuePinReliabilityJob(
                issue_pin_id=issue_pin.issue_pin_id,
                pin_id=pin.pin_id,
                title=safe_title,
                content=safe_content,
                user_gps=user_gps,
                user_address=user_address,
            ),
            background_tasks=background_tasks,
        )

        image_status = (
            ImageUploadStatus.COMPLETED if image_snapshots else ImageUploadStatus.NONE
        )
        return await self._build_issue_pin_home_response(
            uid=uid,
            pin=pin,
            issue_pin=issue_pin,
            pin_location=pin_location,
            pin_user_nickname=user.nickname,
            pin_images=saved_images,
            reliability_status=ReliabilityStatus.PENDING,
            image_upload_status=image_status,
        )

    async def _build_issue_pin_home_response(
        self,
        *,
        uid: str,
        pin: Pin,
        issue_pin: IssuePin,
        pin_location: PinLocation | None,
        pin_user_nickname: str | None = None,
        pin_images: list[PinImage] | None = None,
        reliability_status: ReliabilityStatus | None = None,
        image_upload_status: ImageUploadStatus | None = None,
    ) -> IssuePinHomeDetailResponse:
        detail_address = pin_location.detail_address if pin_location is not None else None

        image_rows = pin_images if pin_images is not None else []
        pin_images_sorted = sorted(
            image_rows,
            key=lambda img: (not img.is_main, img.pin_image_id),
        )
        image_items = [
            IssuePinHomeImageItem(
                pin_image_id=img.pin_image_id,
                pin_image_url=img.pin_s3_url,
                is_main=img.is_main,
            )
            for img in pin_images_sorted
        ]

        resolved_reliability = reliability_status
        if resolved_reliability is None:
            resolved_reliability = self._derive_reliability_status(
                issue_confidence=issue_pin.issue_confidence,
                confidence_content=issue_pin.confidence_content,
            )
        resolved_image_status = image_upload_status
        if resolved_image_status is None:
            resolved_image_status = self._derive_image_upload_status(
                pin_images_count=len(image_items),
                reliability_status=resolved_reliability,
            )

        is_like = await self._pin_like_repo.exists_like(pin_id=pin.pin_id, uid=uid)
        community_id = await self._community_repo.get_community_id_by_pin_id(pin.pin_id)

        return IssuePinHomeDetailResponse(
            issue_pin_id=issue_pin.issue_pin_id,
            pin_id=pin.pin_id,
            pin_type=pin.pin_type.value,
            pin_title=pin.pin_title,
            pin_content=pin.pin_content,
            issue_pin_state=issue_pin.issue_pin_state.value,
            pin_detail_address=detail_address,
            like_count=pin.like_count,
            is_like=is_like,
            pin_user_id=pin.uid,
            pin_user_profile=None,
            pin_user_nickname=pin_user_nickname,
            pin_image_urls=image_items,
            is_updated=self._is_pin_updated(
                created_at=pin.created_at,
                updated_at=pin.updated_at,
            ),
            created_at=self._format_pin_datetime(pin.created_at) or "",
            updated_at=self._format_pin_datetime(pin.updated_at),
            view=pin.view_count,
            is_reported=False,
            is_mine=pin.uid == uid,
            community_id=community_id,
            reliability_status=resolved_reliability,
            image_upload_status=resolved_image_status,
        )

    @staticmethod
    def _derive_reliability_status(
        *,
        issue_confidence: float | None,
        confidence_content: str | None,
    ) -> ReliabilityStatus:
        if issue_confidence is None and not (confidence_content or "").strip():
            return ReliabilityStatus.PENDING
        if is_failed_reliability_content(confidence_content):
            return ReliabilityStatus.FAILED
        return ReliabilityStatus.COMPLETED

    @staticmethod
    def _derive_image_upload_status(
        *,
        pin_images_count: int,
        reliability_status: ReliabilityStatus,
    ) -> ImageUploadStatus:
        if pin_images_count > 0:
            return ImageUploadStatus.COMPLETED
        if reliability_status == ReliabilityStatus.PENDING:
            return ImageUploadStatus.PENDING
        return ImageUploadStatus.NONE

    async def get_issue_pin_detail(
        self,
        *,
        uid: str,
        issue_pin_id: int,
    ) -> IssuePinHomeDetailResponse:
        issue_pin = await self._issue_pin_repo.get_by_issue_pin_id(issue_pin_id)
        if issue_pin is None or issue_pin.pin is None:
            raise_business_exception(ErrorCode.ISSUE_NOT_FOUND)

        pin = issue_pin.pin
        return await self._build_issue_pin_home_response(
            uid=uid,
            pin=pin,
            issue_pin=issue_pin,
            pin_location=pin.pin_location,
            pin_user_nickname=pin.user.nickname if pin.user is not None else None,
            pin_images=list(pin.pin_images or []),
        )

    async def get_issue_pin_reliability(
        self,
        *,
        uid: str,
        issue_pin_id: int,
    ) -> IssuePinReliabilityResponse:
        issue_pin = await self._issue_pin_repo.get_by_issue_pin_id(issue_pin_id)
        if issue_pin is None or issue_pin.pin is None:
            raise_business_exception(ErrorCode.ISSUE_NOT_FOUND)

        pin = issue_pin.pin
        pin_images = list(pin.pin_images or [])
        reliability = self._derive_reliability_status(
            issue_confidence=issue_pin.issue_confidence,
            confidence_content=issue_pin.confidence_content,
        )
        image_status = self._derive_image_upload_status(
            pin_images_count=len(pin_images),
            reliability_status=reliability,
        )

        return IssuePinReliabilityResponse(
            issue_pin_id=issue_pin.issue_pin_id,
            pin_id=pin.pin_id,
            issue_confidence=issue_pin.issue_confidence,
            confidence_content=issue_pin.confidence_content,
            reliability_status=reliability,
            image_upload_status=image_status,
        )
