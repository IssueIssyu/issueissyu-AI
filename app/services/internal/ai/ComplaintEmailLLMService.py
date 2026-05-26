from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException, raise_business_exception
from app.schemas.ComplaintEmailDTO import ComplaintEmailLlmBundle
from app.services.internal.ComplaintEmailOpinionRenderer import (
    ComplaintEmailOpinionRenderer,
    OpinionAttachmentImage,
)
from app.services.internal.ai.gemini_retry import generate_content_with_retry
from app.services.prompts.complaint_email_opinion import complaint_opinion_prompt

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


@dataclass(slots=True)
class ComplaintEmailLLMService:
    api_key: str
    model_name: str = "gemini-2.5-flash"
    client: genai.Client = field(init=False, repr=False)
    _opinion_renderer: ComplaintEmailOpinionRenderer = field(
        default_factory=ComplaintEmailOpinionRenderer,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    async def generate_opinion_html(
        self,
        bundle: ComplaintEmailLlmBundle,
        *,
        attachment_images: list[OpinionAttachmentImage] | None = None,
        submitter_name: str | None = None,
        submitter_address: str | None = None,
        submitter_phone: str | None = None,
    ) -> str:
        prompt = complaint_opinion_prompt(bundle)
        raw = await self._generate_json_text(prompt)
        try:
            sections = self._opinion_renderer.parse_sections_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "의견서 JSON 파싱 실패") from exc
        sections["submitter_name"] = self._as_nullable_text(submitter_name)
        sections["submitter_address"] = self._as_nullable_text(submitter_address)
        sections["submitter_phone"] = self._as_nullable_text(submitter_phone)
        return self._opinion_renderer.render(
            bundle,
            sections,
            attachment_images=attachment_images,
        )

    async def _generate_json_text(self, prompt: str) -> str:
        text = (prompt or "").strip()
        if not text:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, "LLM 프롬프트가 비어 있습니다.")

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
        )
        try:
            response = await generate_content_with_retry(
                self.client,
                model_name=self.model_name,
                fallback_models=(),
                contents=text,
                config=config,
                log_prefix="ComplaintEmailLLM",
            )
        except genai_errors.APIError as exc:
            raise BusinessException(
                ErrorCode.ISSUE_PIN_LLM_BLOCKED,
                f"의견서 LLM 호출 실패: {exc}",
            ) from exc

        try:
            raw = response.text
        except (ValueError, AttributeError) as exc:
            raise BusinessException(
                ErrorCode.ISSUE_PIN_LLM_BLOCKED,
                str(exc) if str(exc) else None,
            ) from exc

        out = _JSON_FENCE_RE.sub("", (raw or "").strip())
        if not out:
            raise_business_exception(ErrorCode.ISSUE_PIN_LLM_NO_OUTPUT)
        return out

    @staticmethod
    def _as_nullable_text(value: str | None) -> str:
        if value is None:
            return ""
        return value.strip()
