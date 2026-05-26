from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException, raise_business_exception
from app.schemas.ComplaintEmailDTO import (
    ComplaintEmailVlmOutput,
    ComplaintEmailVlmImageSlot,
    ComplaintEmailVlmInput,
)
from app.schemas.IssueDTO import ImageWithLocation
from app.services.internal.ai.gemini_retry import generate_content_with_retry
from app.services.internal.ai.VLMService import resolve_upload_image_mime
from app.services.prompts.complaint_email_vlm import (
    ComplaintEmailVlmCatalog,
    ComplaintEmailVlmPromptBuilder,
)

logger = logging.getLogger(__name__)

class ComplaintEmailVlmResultProcessor:
    def __init__(self, catalog: type[ComplaintEmailVlmCatalog] = ComplaintEmailVlmCatalog) -> None:
        self._catalog = catalog

    def parse_model_output(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "VLM JSON 파싱 실패") from exc
        if not isinstance(data, dict):
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "VLM 응답이 객체가 아닙니다.")
        return data

    def normalize(self, data: dict[str, Any]) -> ComplaintEmailVlmOutput:
        catalog = self._catalog
        type_value = self._pick_enum(data.get("type"), catalog.CATEGORY_TYPES, catalog.DEFAULT_TYPE)
        domain_value = self._pick_enum(data.get("domain"), catalog.ADMIN_DOMAINS, catalog.DEFAULT_DOMAIN)
        if type_value in catalog.TYPE_PLAUSIBLE_DOMAINS:
            allowed = catalog.TYPE_PLAUSIBLE_DOMAINS[type_value]
            if domain_value not in allowed:
                domain_value = catalog.TYPE_DOMAIN_FALLBACK.get(type_value, catalog.DEFAULT_DOMAIN)
        subcategory = self._clean_str(data.get("subcategory"))
        summary = self._clean_str(data.get("summary")) or ""
        objects = self._clean_str_list(data.get("objects"))
        keywords = self._clean_keywords(data.get("keywords"))
        query = self._clean_str(data.get("query")) or summary[:50] or type_value
        return ComplaintEmailVlmOutput(
            type=type_value,
            domain=domain_value,
            subcategory=subcategory,
            summary=summary,
            objects=objects,
            keywords=keywords,
            query=query,
        )

    @staticmethod
    def _pick_enum(value: Any, allowed: tuple[str, ...], default: str) -> str:
        if isinstance(value, str) and value.strip() in allowed:
            return value.strip()
        return default

    @staticmethod
    def _clean_str(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None

    def _clean_str_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            s = self._clean_str(item)
            if s:
                out.append(s)
        return out

    def _clean_keywords(self, value: Any) -> list[str]:
        raw = self._clean_str_list(value)
        banned = {"문제", "민원", "사진", "이미지", "불편", "확인"}
        out: list[str] = []
        for kw in raw:
            if kw in banned or kw in out:
                continue
            out.append(kw)
            if len(out) >= self._catalog.KEYWORDS_MAX:
                break
        return out


class ComplaintEmailVlmService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        catalog: type[ComplaintEmailVlmCatalog] = ComplaintEmailVlmCatalog,
        prompt_builder: ComplaintEmailVlmPromptBuilder | None = None,
        result_processor: ComplaintEmailVlmResultProcessor | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._catalog = catalog
        self._prompt_builder = prompt_builder or ComplaintEmailVlmPromptBuilder(catalog)
        self._processor = result_processor or ComplaintEmailVlmResultProcessor(catalog)
        self._client: genai.Client | None = None
        if api_key:
            self._client = genai.Client(api_key=api_key)

    def _ensure_client(self) -> genai.Client:
        if self._client is None:
            raise_business_exception(ErrorCode.VLM_NOT_CONFIGURED)
        return self._client

    @staticmethod
    def prepare_images(images: list[ImageWithLocation]) -> list[ImageWithLocation]:
        return [img for img in images if img.image is not None]

    def build_request(
        self,
        *,
        pin_title: str,
        pin_content: str,
        images: list[ImageWithLocation],
        photo_address: str | None = None,
    ) -> ComplaintEmailVlmInput:
        slots: list[ComplaintEmailVlmImageSlot] = []
        for idx, img in enumerate(images, start=1):
            upload = img.image
            slots.append(
                ComplaintEmailVlmImageSlot(
                    index=idx,
                    filename=(upload.filename if upload else None) or f"image_{idx}",
                    photo_address=img.address,
                ),
            )
        if photo_address is None:
            for slot in slots:
                if slot.photo_address:
                    photo_address = slot.photo_address
                    break
        return ComplaintEmailVlmInput(
            pin_title=pin_title.strip(),
            pin_content=pin_content.strip(),
            photo_address=photo_address,
            image_slots=slots,
        )

    async def analyze(
        self,
        request: ComplaintEmailVlmInput,
        images: list[ImageWithLocation],
    ) -> ComplaintEmailVlmOutput:
        prompt = self._prompt_builder.build_from_input(request)
        raw = await self._call_vlm(prompt, images)
        data = self._processor.parse_model_output(raw)
        return self._processor.normalize(data)

    async def _call_vlm(self, prompt: str, images: list[ImageWithLocation]) -> str:
        client = self._ensure_client()
        parts: list[Any] = []
        for idx, img in enumerate(images, start=1):
            upload = img.image
            image_bytes = await upload.read()
            if not image_bytes:
                raise BusinessException(
                    ErrorCode.VALIDATION_ERROR,
                    f"업로드 이미지가 비어 있습니다. (인덱스 {idx})",
                )
            mime = resolve_upload_image_mime(upload)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
            await upload.seek(0)
        parts.append(prompt)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=self._catalog.response_json_schema(),
        )

        try:
            response = await generate_content_with_retry(
                client,
                model_name=self._model,
                fallback_models=(),
                contents=parts,
                config=config,
                log_prefix="ComplaintEmailVLM",
            )
        except genai_errors.APIError as exc:
            raise BusinessException(
                ErrorCode.ISSUE_PIN_LLM_BLOCKED,
                f"민원 분석 VLM 호출 실패: {exc}",
            ) from exc

        try:
            raw_text = response.text
        except (ValueError, AttributeError) as exc:
            raise BusinessException(
                ErrorCode.ISSUE_PIN_LLM_BLOCKED,
                str(exc) if str(exc) else None,
            ) from exc
        text = (raw_text or "").strip()
        if not text:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "VLM 응답이 비어 있습니다.")
        return text
