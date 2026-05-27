from __future__ import annotations

import asyncio
import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, UploadFile

from app.core.config import settings
from app.core.codes import ErrorCode
from app.core.exceptions import (
    BusinessException,
    raise_business_exception,
    raise_validation_exception,
)
from app.models.IssuePin import IssuePin
from app.models.Pin import Pin
from app.models.PinImage import PinImage
from app.models.PinLocation import PinLocation
from app.models.enum.IssuePinState import IssuePinState
from app.models.enum.PinType import PinType
from app.models.enum.ToneType import ToneType
from app.repositories.CommunityRepo import CommunityRepo
from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.PinLikeRepo import PinLikeRepo
from app.repositories.PinImageRepo import PinImageRepo
from app.repositories.PinLocationRepo import PinLocationRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.utils.S3Util import S3Util
from app.schemas.IssueDTO import (
    CreateIssuePinMultipartRequest,
    CreateIssuePinRequest,
    ImageUploadStatus,
    IssueAnalysisResult,
    IssuePinHomeDetailResponse,
    IssuePinHomeImageItem,
    IssuePinReliabilityResponse,
    ReliabilityStatus,
    UpdateIssuePinMultipartRequest,
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
from app.utils.geo import user_gps_from_wgs84, wgs84_from_pin_point, wkt_point_from_wgs84

logger = logging.getLogger(__name__)
SINGLE_RETRIEVAL_TOP_K = 5
S3_ISSUE_IMAGE_PREFIX = "issueimage"
MAX_PIN_IMAGE_TOTAL_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _UpdatePinImagePlan:
    images_unchanged: bool
    kept: tuple[tuple[PinImage, bool], ...]
    new: tuple[tuple[ImageSnapshot, bool], ...]
    removed_s3_keys: tuple[str, ...]


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
        # DB/driver 설정에 따라 naive/aware datetime이 혼재할 수 있어 비교 전에 정규화한다.
        normalized_created_at = created_at
        normalized_updated_at = updated_at
        if normalized_created_at.tzinfo is None:
            normalized_created_at = normalized_created_at.replace(tzinfo=ZoneInfo("UTC"))
        if normalized_updated_at.tzinfo is None:
            normalized_updated_at = normalized_updated_at.replace(tzinfo=ZoneInfo("UTC"))
        return normalized_updated_at > normalized_created_at

    @staticmethod
    def _user_coordinates_from_request(request: CreateIssuePinRequest) -> str:
        return user_gps_from_wgs84(
            latitude=request.latitude,
            longitude=request.longitude,
        )

    async def _resolve_user_location_address(
        self,
        request: CreateIssuePinRequest,
    ) -> str | None:
        resolved = await self._location_resolve_client.resolve_wgs84(
            latitude=request.latitude,
            longitude=request.longitude,
        )
        if resolved is None:
            return None
        address = (resolved.address or "").strip()
        return address or None

    async def _resolve_location_fields(
        self,
        request: CreateIssuePinRequest,
    ) -> tuple[int, str, str]:
        return await self._resolve_location_fields_from_coords(
            latitude=request.latitude,
            longitude=request.longitude,
            failure_error=ErrorCode.VALIDATION_ERROR,
        )

    async def _resolve_location_fields_from_coords(
        self,
        *,
        latitude: float,
        longitude: float,
        failure_error: ErrorCode = ErrorCode.ISSUE_PIN_IMPORT_FAILED,
    ) -> tuple[int, str, str]:
        resolved = await self._location_resolve_client.resolve_wgs84(
            latitude=latitude,
            longitude=longitude,
        )
        if resolved is None:
            if failure_error == ErrorCode.VALIDATION_ERROR:
                raise_validation_exception(
                    failure_error,
                    detail="위치를 확인할 수 없습니다. 좌표를 다시 확인해 주세요.",
                )
            raise_business_exception(failure_error)
        detail_address = (resolved.address or "").strip()
        if not detail_address:
            if failure_error == ErrorCode.VALIDATION_ERROR:
                raise_validation_exception(
                    failure_error,
                    detail="위치 주소를 확인할 수 없습니다.",
                )
            raise_business_exception(failure_error)
        location_id = resolved.location_id
        if location_id is None:
            if failure_error == ErrorCode.VALIDATION_ERROR:
                raise_validation_exception(
                    failure_error,
                    detail="위치 정보를 확인할 수 없습니다. 좌표를 다시 확인해 주세요.",
                )
            raise_business_exception(failure_error)
        trimmed_address = detail_address[:150]
        return location_id, trimmed_address, trimmed_address

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

    async def _upload_snapshot_to_s3(self, snap: ImageSnapshot) -> dict[str, str]:
        return await self._s3_util.upload_bytes(
            snap.data,
            filename=snap.filename,
            content_type=snap.content_type,
            prefix=S3_ISSUE_IMAGE_PREFIX,
        )

    @staticmethod
    def _validate_pin_text(
        *,
        pin_title: str,
        pin_content: str,
        validation_error: ErrorCode,
    ) -> tuple[str, str]:
        safe_title = pin_title.strip()
        safe_content = pin_content.strip()
        if not safe_title or not safe_content:
            raise_business_exception(validation_error)
        if len(safe_title) > settings.pin_title_max_length:
            raise_business_exception(validation_error)
        if len(safe_content) > settings.pin_content_max_length:
            raise_business_exception(validation_error)
        return safe_title, safe_content

    @staticmethod
    def _validate_update_issue_pin_text(*, pin_title: str, pin_content: str) -> tuple[str, str]:
        return IssueService._validate_pin_text(
            pin_title=pin_title,
            pin_content=pin_content,
            validation_error=ErrorCode.ISSUE_PIN_EDIT_VALIDATION,
        )

    @staticmethod
    def _validate_pin_image_main_flags(
        *main_flags: bool,
        error_code: ErrorCode = ErrorCode.ISSUE_PIN_EDIT_VALIDATION,
    ) -> None:
        if not main_flags:
            return
        main_count = sum(1 for flag in main_flags if flag)
        if main_count != 1:
            raise_business_exception(error_code)

    @staticmethod
    async def _snapshot_update_photos(photos: list[UploadFile]) -> tuple[ImageSnapshot, ...]:
        snapshots: list[ImageSnapshot] = []
        total_bytes = 0
        for index, upload in enumerate(photos, start=1):
            raw = await upload.read()
            if not raw:
                if not (upload.filename or "").strip():
                    continue
                raise_business_exception(ErrorCode.PIN_IMAGE_UPLOAD_FAILED)
            extension = Path(upload.filename or "").suffix.lower()
            if extension not in S3Util.ALLOWED_IMAGE_EXTENSIONS:
                raise_business_exception(ErrorCode.PIN_IMAGE_UPLOAD_FAILED)
            mime = (upload.content_type or "").split(";")[0].strip().lower()
            if not mime:
                guessed, _ = mimetypes.guess_type(upload.filename or "")
                mime = (guessed or "").split(";")[0].strip().lower()
            if not mime.startswith("image/"):
                raise_business_exception(ErrorCode.PIN_IMAGE_UPLOAD_FAILED)
            total_bytes += len(raw)
            if total_bytes > MAX_PIN_IMAGE_TOTAL_BYTES:
                raise_business_exception(ErrorCode.PIN_IMAGE_TOTAL_SIZE_EXCEEDED)
            name = upload.filename or f"image_{index}.jpg"
            snapshots.append(
                ImageSnapshot(data=raw, content_type=mime, filename=name),
            )
        return tuple(snapshots)

    async def _build_update_pin_image_plan(
        self,
        *,
        pin_id: int,
        existing_images: list[PinImage],
        request: UpdateIssuePinMultipartRequest,
        photos: list[UploadFile],
    ) -> _UpdatePinImagePlan:
        if request.pin_image_urls is None and not photos:
            return _UpdatePinImagePlan(
                images_unchanged=True,
                kept=tuple(),
                new=tuple(),
                removed_s3_keys=tuple(),
            )

        kept_specs: list[tuple[PinImage, bool]] = []
        if request.pin_image_urls is None:
            kept_specs = [(img, img.is_main) for img in existing_images]
        else:
            seen_urls: set[str] = set()
            seen_ids: set[int] = set()
            for item in request.pin_image_urls:
                url = item.pin_image_url.strip()
                if not url or url in seen_urls:
                    raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_VALIDATION)
                seen_urls.add(url)
                row = await self._pin_image_repo.get_by_pin_id_and_url(pin_id, url)
                if row is None:
                    raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_VALIDATION)
                if row.pin_image_id in seen_ids:
                    raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_VALIDATION)
                seen_ids.add(row.pin_image_id)
                kept_specs.append((row, item.is_main))

        if request.pin_images and not photos:
            raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_VALIDATION)

        new_specs: list[tuple[ImageSnapshot, bool]] = []
        if photos:
            pin_images_meta = request.pin_images
            if pin_images_meta is None:
                raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_VALIDATION)
            snapshots = await self._snapshot_update_photos(photos)
            if not snapshots:
                raise_business_exception(ErrorCode.PIN_IMAGE_UPLOAD_FAILED)
            if len(snapshots) != len(pin_images_meta):
                raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_VALIDATION)
            new_specs = [
                (snapshots[index], pin_images_meta[index].is_main)
                for index in range(len(snapshots))
            ]

        total_count = len(kept_specs) + len(new_specs)
        if total_count > settings.issue_pin_max_images:
            raise_business_exception(ErrorCode.PIN_IMAGE_COUNT_EXCEEDED)

        self._validate_pin_image_main_flags(
            *[is_main for _, is_main in kept_specs],
            *[is_main for _, is_main in new_specs],
        )

        kept_ids = {row.pin_image_id for row, _ in kept_specs}
        removed_s3_keys = tuple(
            (img.pin_s3_key or "").strip()
            for img in existing_images
            if img.pin_image_id not in kept_ids and (img.pin_s3_key or "").strip()
        )

        return _UpdatePinImagePlan(
            images_unchanged=False,
            kept=tuple(kept_specs),
            new=tuple(new_specs),
            removed_s3_keys=removed_s3_keys,
        )

    async def _upload_new_pin_images_with_is_main(
        self,
        *,
        pin_id: int,
        new_specs: tuple[tuple[ImageSnapshot, bool], ...],
    ) -> tuple[list[PinImage], list[str]]:
        if not new_specs:
            return [], []

        uploaded_keys: list[str] = []

        async def upload_and_track(snap: ImageSnapshot) -> dict[str, str]:
            uploaded = await self._upload_snapshot_to_s3(snap)
            uploaded_keys.append(uploaded["key"])
            return uploaded

        try:
            uploaded_list = await asyncio.gather(
                *[upload_and_track(snap) for snap, _ in new_specs],
            )
        except Exception:
            if uploaded_keys:
                await self._s3_util.delete_objects_best_effort(uploaded_keys)
            logger.exception("issue pin image S3 upload failed pin_id=%s", pin_id)
            raise_business_exception(ErrorCode.PIN_IMAGE_UPLOAD_FAILED)

        saved: list[PinImage] = []
        for (snap, is_main), uploaded in zip(new_specs, uploaded_list, strict=True):
            pin_image = PinImage(
                pin_id=pin_id,
                pin_s3_key=uploaded["key"],
                pin_s3_url=uploaded["url"],
                is_main=is_main,
            )
            saved.append(pin_image)
        return saved, uploaded_keys

    async def _sync_pin_images_after_update(
        self,
        *,
        pin_id: int,
        plan: _UpdatePinImagePlan,
    ) -> tuple[list[PinImage], list[str]]:
        new_rows, new_s3_keys = await self._upload_new_pin_images_with_is_main(
            pin_id=pin_id,
            new_specs=plan.new,
        )
        try:
            kept_ids = {row.pin_image_id for row, _ in plan.kept}
            all_existing = await self._pin_image_repo.list_by_pin_id(pin_id)
            remove_ids = [
                img.pin_image_id
                for img in all_existing
                if img.pin_image_id not in kept_ids
            ]
            if remove_ids:
                await self._pin_image_repo.delete_by_ids(remove_ids)

            for row, is_main in plan.kept:
                row.is_main = is_main
                await self._pin_image_repo.save(row, flush_immediately=True)

            for pin_image in new_rows:
                await self._pin_image_repo.save(pin_image, flush_immediately=True)
        except Exception:
            if new_s3_keys:
                await self._s3_util.delete_objects_best_effort(new_s3_keys)
            logger.exception("issue pin update image DB sync failed pin_id=%s", pin_id)
            raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_FAILED)

        saved_images = [row for row, _ in plan.kept]
        saved_images.extend(new_rows)
        return saved_images, new_s3_keys

    async def _cleanup_removed_pin_images_best_effort(
        self,
        *,
        pin_id: int,
        removed_s3_keys: tuple[str, ...],
    ) -> None:
        """commit 성공 후 제거된 핀 이미지 S3 객체를 best-effort로 삭제한다.

        DB 커밋 이후에만 호출해야 한다. 실패해도 API 응답은 성공으로 유지하고
        로그만 남긴다(고아 객체는 운영 모니터링·별도 배치 정리 대상).
        """
        if not removed_s3_keys:
            return
        requested = len(removed_s3_keys)
        try:
            deleted_count = await self._s3_util.delete_objects_best_effort(
                list(removed_s3_keys),
            )
        except Exception:
            logger.exception(
                "issue pin update removed image S3 cleanup failed pin_id=%s requested=%s",
                pin_id,
                requested,
            )
            return

        if deleted_count < requested:
            logger.warning(
                "issue pin update removed image S3 cleanup incomplete pin_id=%s deleted=%s requested=%s",
                pin_id,
                deleted_count,
                requested,
            )
        else:
            logger.info(
                "issue pin update removed image S3 cleanup pin_id=%s deleted=%s requested=%s",
                pin_id,
                deleted_count,
                requested,
            )

    @staticmethod
    def _user_gps_from_pin_location(pin_location: PinLocation | None) -> str:
        if pin_location is None:
            raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_FAILED)
        latitude, longitude = wgs84_from_pin_point(pin_location.pin_point)
        return user_gps_from_wgs84(latitude=latitude, longitude=longitude)

    async def create_issue_pin(
        self,
        *,
        uid: str,
        request: CreateIssuePinMultipartRequest,
        photos: list[UploadFile] | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> IssuePinHomeDetailResponse:
        uploads = photos or []
        safe_title, safe_content = self._validate_pin_text(
            pin_title=request.pin_title,
            pin_content=request.pin_content,
            validation_error=ErrorCode.ISSUE_PIN_IMPORT_VALIDATION,
        )
        if len(uploads) > settings.issue_pin_max_images:
            raise_business_exception(ErrorCode.PIN_IMAGE_COUNT_EXCEEDED)
        if len(uploads) != len(request.pin_images):
            raise_business_exception(ErrorCode.ISSUE_PIN_IMPORT_VALIDATION)
        self._validate_pin_image_main_flags(
            *[item.is_main for item in request.pin_images],
            error_code=ErrorCode.ISSUE_PIN_IMPORT_VALIDATION,
        )

        user = await self._user_repo.get_by_uid(uid)
        if user is None:
            raise_business_exception(ErrorCode.USER_NOT_FOUND)

        location_id, detail_address, user_address = await self._resolve_location_fields_from_coords(
            latitude=request.lat,
            longitude=request.lng,
        )
        user_gps = user_gps_from_wgs84(latitude=request.lat, longitude=request.lng)

        image_specs: tuple[tuple[ImageSnapshot, bool], ...] = ()
        if uploads:
            snapshots = await self._snapshot_update_photos(uploads)
            if len(snapshots) != len(request.pin_images):
                raise_business_exception(ErrorCode.ISSUE_PIN_IMPORT_VALIDATION)
            image_specs = tuple(
                (snapshots[index], request.pin_images[index].is_main)
                for index in range(len(snapshots))
            )

        pin = Pin(
            uid=uid,
            pin_type=PinType.ISSUE,
            pin_title=safe_title,
            pin_content=safe_content,
            tone_type=ToneType.NONE,
            like_count=0,
            view_count=0,
        )

        uploaded_keys: list[str] = []
        saved_images: list[PinImage] = []
        issue_pin: IssuePin
        pin_location: PinLocation
        try:
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
                    latitude=request.lat,
                    longitude=request.lng,
                ),
            )
            await self._pin_location_repo.save(pin_location, flush_immediately=True)

            if image_specs:
                saved_images, uploaded_keys = await self._upload_new_pin_images_with_is_main(
                    pin_id=pin.pin_id,
                    new_specs=image_specs,
                )
                for pin_image in saved_images:
                    await self._pin_image_repo.save(pin_image, flush_immediately=True)

            await self._pin_repo.commit()
        except BusinessException:
            await self._pin_repo.rollback()
            if uploaded_keys:
                await self._s3_util.delete_objects_best_effort(uploaded_keys)
            raise
        except Exception:
            await self._pin_repo.rollback()
            if uploaded_keys:
                await self._s3_util.delete_objects_best_effort(uploaded_keys)
            logger.exception("issue pin create commit failed uid=%s", uid)
            raise_business_exception(ErrorCode.ISSUE_PIN_IMPORT_FAILED)

        await self._background_runner.schedule(
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

        image_status = ImageUploadStatus.COMPLETED if saved_images else ImageUploadStatus.NONE
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

    async def update_issue_pin(
        self,
        *,
        uid: str,
        pin_id: int,
        request: UpdateIssuePinMultipartRequest,
        photos: list[UploadFile] | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> IssuePinHomeDetailResponse:
        uploads = photos or []
        user = await self._user_repo.get_by_uid(uid)
        if user is None:
            raise_business_exception(ErrorCode.USER_NOT_FOUND)

        safe_title, safe_content = self._validate_update_issue_pin_text(
            pin_title=request.pin_title,
            pin_content=request.pin_content,
        )
        issue_pin = await self._issue_pin_repo.get_by_pin_id(pin_id)
        if issue_pin is None or issue_pin.pin is None:
            raise_business_exception(ErrorCode.ISSUE_NOT_FOUND)

        pin = issue_pin.pin
        if pin.pin_type != PinType.ISSUE:
            raise_business_exception(ErrorCode.ISSUE_NOT_FOUND)
        if pin.uid != uid:
            raise_business_exception(ErrorCode.FORBIDDEN)
        if issue_pin.issue_pin_state != IssuePinState.BEFORE_PROGRESS:
            raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_VALIDATION)

        pin_location = pin.pin_location
        if pin_location is None:
            raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_FAILED)

        existing_images = list(pin.pin_images or [])
        image_plan = await self._build_update_pin_image_plan(
            pin_id=pin.pin_id,
            existing_images=existing_images,
            request=request,
            photos=uploads,
        )

        uploaded_keys: list[str] = []
        saved_images: list[PinImage]
        try:
            if safe_title != pin.pin_title or safe_content != pin.pin_content:
                pin.pin_title = safe_title
                pin.pin_content = safe_content
                await self._pin_repo.save(pin, flush_immediately=True)

            if image_plan.images_unchanged:
                saved_images = existing_images
            else:
                saved_images, uploaded_keys = await self._sync_pin_images_after_update(
                    pin_id=pin.pin_id,
                    plan=image_plan,
                )

            user_gps = self._user_gps_from_pin_location(pin_location)
            user_address = (pin_location.detail_address or "").strip() or None

            await self._issue_pin_repo.reset_confidence(issue_pin.issue_pin_id)
            await self._background_runner.cancel(pin_id=pin.pin_id)
            await self._pin_repo.commit()
        except BusinessException:
            await self._pin_repo.rollback()
            if uploaded_keys:
                await self._s3_util.delete_objects_best_effort(uploaded_keys)
            raise
        except Exception:
            await self._pin_repo.rollback()
            if uploaded_keys:
                await self._s3_util.delete_objects_best_effort(uploaded_keys)
            logger.exception("issue pin update failed pin_id=%s", pin.pin_id)
            raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_FAILED)

        await self._cleanup_removed_pin_images_best_effort(
            pin_id=pin.pin_id,
            removed_s3_keys=image_plan.removed_s3_keys,
        )

        await self._background_runner.schedule(
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
            ImageUploadStatus.COMPLETED if saved_images else ImageUploadStatus.NONE
        )

        return await self._build_issue_pin_home_response(
            uid=uid,
            pin=pin,
            issue_pin=issue_pin,
            pin_location=pin_location,
            pin_user_nickname=pin.user.nickname if pin.user is not None else None,
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
        pin_id: int,
    ) -> IssuePinReliabilityResponse:
        _ = uid
        issue_pin = await self._issue_pin_repo.get_by_pin_id(pin_id)
        if issue_pin is None or issue_pin.pin is None:
            raise_business_exception(ErrorCode.ISSUE_NOT_FOUND)

        pin = issue_pin.pin
        if pin.pin_type != PinType.ISSUE:
            raise_business_exception(ErrorCode.ISSUE_NOT_FOUND)
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
