from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any

from google import genai
from google.genai import types

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException, raise_business_exception
from app.services.internal.ai.gemini_key_pool import GeminiKeyPool
from app.services.internal.ai.gemini_retry import generate_content_with_retry
from app.services.prompts.issue_pin import ISSUE_PIN_OUTPUT_SCHEMA

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IssuePinLLMService:
    """커뮤니티 핀 문구용 텍스트 전용 Gemini 호출 (VLM과 모델·역할 분리)."""

    api_key: str
    model_name: str = "gemini-2.5-flash"
    key_pool: GeminiKeyPool | None = None
    client: genai.Client = field(init=False, repr=False)
    fallback_models: tuple[str, ...] = ("gemini-2.5-flash-lite", "gemini-2.5-flash")

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    async def _generate_with_retry(
        self,
        *,
        contents: str,
        config: types.GenerateContentConfig | None = None,
    ):
        return await generate_content_with_retry(
            self.client,
            model_name=self.model_name,
            fallback_models=self.fallback_models,
            contents=contents,
            config=config,
            log_prefix="Pin",
            key_pool=self.key_pool,
        )

    async def generate_pin_copy(self, *, prompt: str) -> dict[str, str]:
        """`issue_pin_prompt`로 만든 전체 프롬프트를 넣고, 제목·본문 JSON을 받는다."""
        text = (prompt or "").strip()
        if not text:
            raise_business_exception(ErrorCode.ISSUE_PIN_PROMPT_EMPTY)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ISSUE_PIN_OUTPUT_SCHEMA,
        )
        response = await self._generate_with_retry(contents=text, config=config)
        try:
            raw = response.text
        except (ValueError, AttributeError) as exc:
            raise BusinessException(
                ErrorCode.ISSUE_PIN_LLM_BLOCKED,
                str(exc) if str(exc) else None,
            ) from exc

        out = (raw or "").strip()
        if not out:
            raise_business_exception(ErrorCode.ISSUE_PIN_LLM_NO_OUTPUT)

        try:
            parsed: Any = json.loads(out)
        except JSONDecodeError as exc:
            logger.exception("Issue pin LLM JSON parse failed")
            raise BusinessException(ErrorCode.ISSUE_PIN_LLM_NO_OUTPUT) from exc

        if not isinstance(parsed, dict):
            raise_business_exception(ErrorCode.ISSUE_PIN_LLM_NO_OUTPUT)

        title = parsed.get("title")
        content = parsed.get("content")
        if not isinstance(title, str) or not isinstance(content, str):
            raise_business_exception(ErrorCode.ISSUE_PIN_LLM_NO_OUTPUT)

        title_s = title.strip()
        content_s = content.strip()
        if not title_s or not content_s:
            raise_business_exception(ErrorCode.ISSUE_PIN_LLM_NO_OUTPUT)

        return {"title": title_s, "content": content_s}

    async def generate_pin_text(self, *, prompt: str) -> str:
        """축제 핀 등 본문만 필요한 프롬프트용 — plain text 응답."""
        text = (prompt or "").strip()
        if not text:
            raise_business_exception(ErrorCode.ISSUE_PIN_PROMPT_EMPTY)

        response = await self._generate_with_retry(contents=text)
        try:
            raw = response.text
        except (ValueError, AttributeError) as exc:
            raise BusinessException(
                ErrorCode.ISSUE_PIN_LLM_BLOCKED,
                str(exc) if str(exc) else None,
            ) from exc

        out = (raw or "").strip()
        if not out:
            raise_business_exception(ErrorCode.ISSUE_PIN_LLM_NO_OUTPUT)
        return out
