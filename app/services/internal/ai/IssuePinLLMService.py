from __future__ import annotations

import logging
from dataclasses import dataclass, field

from google import genai

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException, raise_business_exception
from app.services.internal.ai.gemini_retry import generate_content_with_retry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IssuePinLLMService:
    """커뮤니티 핀 문구용 텍스트 전용 Gemini 호출 (VLM과 모델·역할 분리)."""

    api_key: str
    model_name: str = "gemini-2.5-flash"
    client: genai.Client = field(init=False, repr=False)
    fallback_models: tuple[str, ...] = ("gemini-2.5-flash-lite", "gemini-2.5-flash")

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    async def _generate_with_retry(self, *, contents: str):
        return await generate_content_with_retry(
            self.client,
            model_name=self.model_name,
            fallback_models=self.fallback_models,
            contents=contents,
            log_prefix="Pin",
        )

    async def generate_pin_text(self, *, prompt: str) -> str:
        """`issue_pin_prompt`로 만든 전체 프롬프트 한 덩어리를 넣고, 핀 본문만 받는다."""
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
