from __future__ import annotations

import logging
from typing import Any

from llama_index.core.vector_stores import MetadataFilter, MetadataFilters

from app.core.codes import ErrorCode
from app.core.exceptions import raise_business_exception
from app.schemas.ComplaintEmailDTO import (
    ComplaintEmailGenerateResult,
    ComplaintEmailLlmBundle,
    ComplaintEmailRagHit,
    ComplaintEmailValidationResult,
    ComplaintEmailVlmOutput,
)
from app.schemas.IssueDTO import ImageWithLocation
from app.services.internal.ai.ComplaintEmailLLMService import ComplaintEmailLLMService
from app.services.internal.ai.ComplaintEmailVLMService import ComplaintEmailVlmService
from app.services.internal.ai.VLMService import VLMService
from app.services.internal.ComplaintEmailPdfService import ComplaintEmailPdfService
from app.services.prompts.issue_pin import format_user_text_for_pin
from app.services.RagRetrievalService import RagRetrievalService
from app.services.vector_domains import VectorDomain

logger = logging.getLogger(__name__)


class ComplaintEmailService:
    def __init__(
        self,
        *,
        complaint_vlm_service: ComplaintEmailVlmService,
        pin_validation_vlm_service: VLMService,
        complaint_llm_service: ComplaintEmailLLMService,
        rag_retrieval_service: RagRetrievalService,
        pdf_service: ComplaintEmailPdfService | None = None,
    ) -> None:
        self._complaint_vlm = complaint_vlm_service
        self._validation_vlm = pin_validation_vlm_service
        self._complaint_llm = complaint_llm_service
        self._rag_retrieval = rag_retrieval_service
        self._pdf_service = pdf_service or ComplaintEmailPdfService()

    async def generate_petition_package(
        self,
        *,
        pin_title: str,
        pin_content: str,
        images: list[ImageWithLocation],
        photo_address: str | None = None,
    ) -> ComplaintEmailGenerateResult:
        title = pin_title.strip()
        content = pin_content.strip()
        if not title or not content:
            raise_business_exception(
                ErrorCode.VALIDATION_ERROR,
                "이슈 핀 제목과 본문이 필요합니다.",
            )

        prepared = ComplaintEmailVlmService.prepare_images(images)
        if not prepared:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, "이미지는 1장 이상 필요합니다.")

        pin_text = format_user_text_for_pin(title=title, content=content)

        vlm_request = self._complaint_vlm.build_request(
            pin_title=title,
            pin_content=content,
            images=prepared,
            photo_address=photo_address,
        )
        vlm_result = await self._complaint_vlm.analyze(vlm_request, prepared)

        rag_query = (vlm_result.query or vlm_result.summary or pin_text).strip()
        filters = self._build_rag_metadata_filters(vlm_result)
        rag_hits = await self._rag_retrieval.retrieve_and_rerank(
            rag_query,
            domain=VectorDomain.COMPLAINT,
            filters=filters,
        )
        logger.info(
            "RAG retrieve+rerank — query=%r, hits=%d",
            rag_query,
            len(rag_hits),
        )

        bundle = ComplaintEmailLlmBundle(
            pin_title=title,
            pin_content=content,
            rag_query=rag_query,
            vlm=vlm_result,
            rag_hits=rag_hits,
        )

        opinion_html = await self._complaint_llm.generate_opinion_html(bundle)

        validation = await self._run_validation_vlm(
            pin_text=pin_text,
            images=prepared,
        )

        opinion_pdf_bytes = await self._pdf_service.html_to_pdf(opinion_html)

        notification_email_body = await self._complaint_llm.generate_notification_email(
            pin_title=title,
            pin_content=content,
            opinion_summary=vlm_result.summary,
            reliability_score=validation.reliability_score,
            validity=validation.validity,
            risk_note=validation.risk_note,
        )

        for row in prepared:
            await row.image.seek(0)

        return ComplaintEmailGenerateResult(
            opinion_html=opinion_html,
            opinion_pdf_bytes=opinion_pdf_bytes,
            notification_email_body=notification_email_body,
            reliability_score=validation.reliability_score,
            llm_bundle=bundle,
            validation=validation,
        )

    async def _run_validation_vlm(
        self,
        *,
        pin_text: str,
        images: list[ImageWithLocation],
    ) -> ComplaintEmailValidationResult:
        # 이슈 핀 생성 시와 동일한 검증 VLM (위치는 사용하지 않음)
        vlm_result = await self._validation_vlm.analyze_image(
            user_text=pin_text.strip(),
            images=images,
            user_location=None,
        )
        score_raw = vlm_result.get("confidence_score")
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        validity = vlm_result.get("validity")
        return ComplaintEmailValidationResult(
            reliability_score=score,
            validity=bool(validity) if isinstance(validity, bool) else False,
            error_code=self._optional_str(vlm_result.get("error_code")),
            scene_summary=self._optional_str(vlm_result.get("scene_summary")),
            risk_note=self._optional_str(vlm_result.get("risk_note")),
        )

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    @staticmethod
    def _build_rag_metadata_filters(
        vlm_result: ComplaintEmailVlmOutput,
    ) -> MetadataFilters | None:
        domain_name = (vlm_result.domain or "").strip()
        if not domain_name or domain_name == "공통":
            return None
        return MetadataFilters(filters=[MetadataFilter(key="category", value=domain_name)])

