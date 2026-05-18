from __future__ import annotations

import asyncio
import io
import logging
import time
from pathlib import Path

from fastapi import BackgroundTasks
from sqlalchemy import select
from starlette.datastructures import Headers, UploadFile

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.PinImage import PinImage
from app.repositories.IssuePinRepo import IssuePinRepo
from app.schemas.IssueDTO import ImageWithLocation
from app.schemas.issue_pin_job import ImageSnapshot, IssuePinReliabilityJob
from app.services.internal.ai.gemini_retry import parse_gemini_model_list
from app.services.internal.ai.IssueRagPlannerService import IssueRagPlannerService
from app.services.internal.ai.VLMService import VLMService
from app.services.internal.geo.ImageExifLocationResolveService import ImageExifLocationResolveService
from app.services.internal.issue_confidence_basis import (
    FAILED_RELIABILITY_BASIS,
    clamp_confidence_score,
    format_confidence_content_for_user,
    resolve_confidence_basis_markdown,
)
from app.services.internal.issue_rag_context import build_rag_context_block_for_reliability
from app.services.prompts.issue_pin import format_user_text_for_pin
from app.services.VectorStoreService import VectorStoreService
from app.utils.S3Util import S3Util

logger = logging.getLogger(__name__)

_RELIABILITY_PIPELINE_TASKS: set[asyncio.Task[None]] = set()


class IssuePinBackgroundRunner:
    def __init__(
        self,
        *,
        vlm_service: VLMService,
        exif_location_service: ImageExifLocationResolveService,
        s3_util: S3Util,
        vector_store_service: VectorStoreService | None,
        issue_rag_planner_service: IssueRagPlannerService | None,
    ) -> None:
        self._vlm_service = vlm_service
        self._exif_location_service = exif_location_service
        self._s3_util = s3_util
        self._vector_store_service = vector_store_service
        self._issue_rag_planner_service = issue_rag_planner_service

    @staticmethod
    def _log_context(job: IssuePinReliabilityJob) -> str:
        return f"issue_pin_id={job.issue_pin_id} pin_id={job.pin_id}"

    def schedule(
        self,
        job: IssuePinReliabilityJob,
        *,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        ctx = self._log_context(job)
        if background_tasks is not None:
            background_tasks.add_task(self.run_reliability_job, job)
            logger.info("Reliability scheduled (BackgroundTasks) [%s]", ctx)
            return

        task = asyncio.create_task(
            self.run_reliability_job(job),
            name=f"issue_pin_reliability_{job.issue_pin_id}",
        )
        _RELIABILITY_PIPELINE_TASKS.add(task)
        task.add_done_callback(_RELIABILITY_PIPELINE_TASKS.discard)
        logger.info("Reliability scheduled (asyncio task) [%s]", ctx)

    async def run_reliability_job(self, job: IssuePinReliabilityJob) -> None:
        ctx = self._log_context(job)
        timeout = settings.issue_pin_reliability_pipeline_timeout_seconds
        pipeline_started = time.monotonic()
        persisted = False
        logger.info(
            "Reliability pipeline job start [%s] total_timeout=%.0fs rag_timeout=%.0fs vlm_timeout=%.0fs "
            "skip_planner=%s gemini_max_attempts=%d",
            ctx,
            timeout,
            settings.issue_pin_reliability_rag_timeout_seconds,
            settings.issue_pin_reliability_vlm_timeout_seconds,
            settings.issue_pin_reliability_skip_rag_planner,
            settings.issue_pin_reliability_gemini_max_attempts,
        )
        try:
            await asyncio.wait_for(self._run_reliability_pipeline(job), timeout=timeout)
            persisted = True
            logger.info(
                "Reliability pipeline job success [%s] elapsed=%.1fs",
                ctx,
                time.monotonic() - pipeline_started,
            )
        except TimeoutError:
            logger.error(
                "Reliability pipeline TOTAL timeout [%s] after %.0fs (rag_limit=%.0fs vlm_limit=%.0fs)",
                ctx,
                timeout,
                settings.issue_pin_reliability_rag_timeout_seconds,
                settings.issue_pin_reliability_vlm_timeout_seconds,
            )
        except asyncio.CancelledError:
            logger.warning("Reliability pipeline cancelled [%s]", ctx)
            raise
        except Exception:
            logger.exception("Reliability pipeline failed [%s]", ctx)
        finally:
            if not persisted:
                logger.warning(
                    "Reliability pipeline persist failure fallback [%s] score=0.0",
                    ctx,
                )
                await self._persist_failure_confidence(issue_pin_id=job.issue_pin_id)
            logger.info(
                "Reliability pipeline job end [%s] persisted=%s elapsed=%.1fs",
                ctx,
                persisted,
                time.monotonic() - pipeline_started,
            )

    async def _run_reliability_pipeline(self, job: IssuePinReliabilityJob) -> None:
        ctx = self._log_context(job)
        user_text = format_user_text_for_pin(title=job.title, content=job.content)

        # --- RAG ---
        rag_started = time.monotonic()
        logger.info("Reliability stage=RAG start [%s]", ctx)
        try:
            rag_block = await asyncio.wait_for(
                self._build_rag_context_block(
                    title=job.title,
                    content=job.content,
                    user_coordinates=job.user_gps,
                    log_context=ctx,
                ),
                timeout=settings.issue_pin_reliability_rag_timeout_seconds,
            )
        except TimeoutError as exc:
            logger.error(
                "Reliability stage=RAG TIMEOUT [%s] after %.0fs",
                ctx,
                settings.issue_pin_reliability_rag_timeout_seconds,
            )
            raise TimeoutError(f"RAG stage timeout [{ctx}]") from exc
        logger.info(
            "Reliability stage=RAG done [%s] elapsed=%.1fs block_chars=%d",
            ctx,
            time.monotonic() - rag_started,
            len(rag_block),
        )

        # --- S3 ---
        s3_started = time.monotonic()
        logger.info("Reliability stage=S3 start [%s]", ctx)
        snapshots = await self._load_snapshots_from_s3(pin_id=job.pin_id, log_context=ctx)
        logger.info(
            "Reliability stage=S3 done [%s] elapsed=%.1fs image_count=%d",
            ctx,
            time.monotonic() - s3_started,
            len(snapshots),
        )

        # --- EXIF ---
        exif_started = time.monotonic()
        logger.info("Reliability stage=EXIF start [%s] image_count=%d", ctx, len(snapshots))
        images_with_location = await self._build_vlm_inputs_from_snapshots(
            snapshots=snapshots,
            log_context=ctx,
        )
        logger.info(
            "Reliability stage=EXIF done [%s] elapsed=%.1fs vlm_input_count=%d",
            ctx,
            time.monotonic() - exif_started,
            len(images_with_location),
        )

        # --- VLM ---
        vlm_started = time.monotonic()
        retry_opts = self._vlm_retry_options()
        logger.info(
            "Reliability stage=VLM start [%s] mode=%s primary=%s fallbacks=%s max_attempts=%d",
            ctx,
            "image" if images_with_location else "text_only",
            self._vlm_service.model_name,
            retry_opts.get("fallback_models"),
            retry_opts.get("max_attempts_per_model"),
        )
        try:
            vlm_result = await asyncio.wait_for(
                self._analyze_reliability(
                    user_text=user_text,
                    user_gps=job.user_gps,
                    user_address=job.user_address,
                    rag_context_block=rag_block,
                    images=images_with_location,
                    log_context=ctx,
                    retry_opts=retry_opts,
                ),
                timeout=settings.issue_pin_reliability_vlm_timeout_seconds,
            )
        except TimeoutError as exc:
            logger.error(
                "Reliability stage=VLM TIMEOUT [%s] after %.0fs",
                ctx,
                settings.issue_pin_reliability_vlm_timeout_seconds,
            )
            raise TimeoutError(f"VLM stage timeout [{ctx}]") from exc
        score = clamp_confidence_score(vlm_result.get("confidence_score"))
        logger.info(
            "Reliability stage=VLM done [%s] elapsed=%.1fs score=%s",
            ctx,
            time.monotonic() - vlm_started,
            score,
        )

        basis_md = resolve_confidence_basis_markdown(
            vlm_result,
            has_images=bool(images_with_location),
            max_chars=settings.issue_confidence_basis_max_chars,
        )
        user_content = format_confidence_content_for_user(
            score=score,
            basis_markdown=basis_md,
        )
        logger.info("Reliability stage=PERSIST start [%s] score=%s", ctx, score)
        await self._persist_confidence(
            issue_pin_id=job.issue_pin_id,
            score=score,
            basis_md=user_content,
            log_context=ctx,
        )

    async def _load_snapshots_from_s3(
        self,
        *,
        pin_id: int,
        log_context: str,
    ) -> tuple[ImageSnapshot, ...]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PinImage)
                .where(PinImage.pin_id == pin_id)
                .order_by(PinImage.is_main.desc(), PinImage.pin_image_id.asc()),
            )
            pin_images = list(result.scalars().all())

        if not pin_images:
            logger.info("Reliability S3: no pin_image rows [%s]", log_context)
            return ()

        snapshots: list[ImageSnapshot] = []
        for pin_image in pin_images:
            logger.info(
                "Reliability S3 download start [%s] key=%s",
                log_context,
                pin_image.pin_s3_key,
            )
            try:
                data, content_type = await self._s3_util.download_bytes(pin_image.pin_s3_key)
            except Exception:
                logger.exception(
                    "Reliability S3 download failed [%s] key=%s",
                    log_context,
                    pin_image.pin_s3_key,
                )
                continue
            if not data:
                logger.warning(
                    "Reliability S3 empty object [%s] key=%s",
                    log_context,
                    pin_image.pin_s3_key,
                )
                continue
            filename = Path(pin_image.pin_s3_key).name or f"pin_{pin_id}.jpg"
            logger.info(
                "Reliability S3 download ok [%s] key=%s bytes=%d mime=%s",
                log_context,
                pin_image.pin_s3_key,
                len(data),
                content_type,
            )
            snapshots.append(
                ImageSnapshot(data=data, content_type=content_type, filename=filename),
            )
        return tuple(snapshots)

    async def _build_rag_context_block(
        self,
        *,
        title: str,
        content: str,
        user_coordinates: str,
        log_context: str,
    ) -> str:
        return await build_rag_context_block_for_reliability(
            vector_store_service=self._vector_store_service,
            issue_rag_planner_service=self._issue_rag_planner_service,
            title=title,
            content=content,
            user_coordinates=user_coordinates,
            log_context=log_context,
        )

    async def _build_vlm_inputs_from_snapshots(
        self,
        *,
        snapshots: tuple[ImageSnapshot, ...],
        log_context: str,
    ) -> list[ImageWithLocation]:
        if not snapshots:
            return ()

        return list(
            await asyncio.gather(
                *[
                    self._build_one_vlm_input(snap, log_context=log_context)
                    for snap in snapshots
                ],
            ),
        )

    async def _build_one_vlm_input(
        self,
        snap: ImageSnapshot,
        *,
        log_context: str,
    ) -> ImageWithLocation:
        logger.info(
            "Reliability EXIF start [%s] filename=%s bytes=%d",
            log_context,
            snap.filename,
            len(snap.data),
        )
        headers = Headers({"content-type": snap.content_type})
        exif_upload = UploadFile(
            file=io.BytesIO(snap.data),
            filename=snap.filename,
            headers=headers,
        )
        exif = await self._exif_location_service.extract_and_resolve(exif_upload)
        address = (exif.address or "").strip() or None
        logger.info(
            "Reliability EXIF done [%s] filename=%s address=%r",
            log_context,
            snap.filename,
            address,
        )
        vlm_upload = UploadFile(
            file=io.BytesIO(snap.data),
            filename=snap.filename,
            headers=headers,
        )
        return ImageWithLocation(image=vlm_upload, address=address)

    def _vlm_retry_options(self) -> dict:
        fallbacks = parse_gemini_model_list(settings.gemini_vlm_fallback_models)
        selected_fallbacks = fallbacks[:1]
        opts = {
            "max_attempts_per_model": settings.issue_pin_reliability_gemini_max_attempts,
            "fallback_models": selected_fallbacks,
        }
        logger.debug(
            "Reliability VLM retry options: max_attempts=%s fallbacks=%s primary=%s",
            opts["max_attempts_per_model"],
            selected_fallbacks,
            self._vlm_service.model_name,
        )
        return opts

    async def _analyze_reliability(
        self,
        *,
        user_text: str,
        user_gps: str,
        user_address: str | None,
        rag_context_block: str,
        images: list[ImageWithLocation],
        log_context: str,
        retry_opts: dict,
    ) -> dict:
        call_kwargs = {**retry_opts, "log_context": log_context}
        if images:
            return await self._vlm_service.analyze_image(
                user_text=user_text,
                images=images,
                user_location=user_gps,
                user_address=user_address,
                rag_context_block=rag_context_block,
                **call_kwargs,
            )
        return await self._vlm_service.analyze_text_only(
            user_text=user_text,
            user_location=user_gps,
            user_address=user_address,
            rag_context_block=rag_context_block,
            **call_kwargs,
        )

    @classmethod
    async def _persist_failure_confidence(cls, *, issue_pin_id: int) -> None:
        try:
            await cls._persist_confidence(
                issue_pin_id=issue_pin_id,
                score=0.0,
                basis_md=FAILED_RELIABILITY_BASIS,
                log_context=f"issue_pin_id={issue_pin_id}",
            )
        except Exception:
            logger.exception(
                "Reliability persist failure record failed issue_pin_id=%s",
                issue_pin_id,
            )

    @staticmethod
    async def _persist_confidence(
        *,
        issue_pin_id: int,
        score: float,
        basis_md: str,
        log_context: str = "",
    ) -> None:
        async with AsyncSessionLocal() as session:
            repo = IssuePinRepo(session)
            try:
                updated = await repo.update_confidence(
                    issue_pin_id,
                    issue_confidence=score,
                    confidence_content=basis_md,
                )
                if not updated:
                    raise RuntimeError(
                        f"issue_pin row not found for confidence update issue_pin_id={issue_pin_id}",
                    )
                await session.commit()
                logger.info(
                    "Reliability stage=PERSIST done [%s] issue_pin_id=%s score=%s",
                    log_context,
                    issue_pin_id,
                    score,
                )
            except Exception:
                await session.rollback()
                logger.exception(
                    "Reliability stage=PERSIST failed [%s] issue_pin_id=%s",
                    log_context,
                    issue_pin_id,
                )
                raise
