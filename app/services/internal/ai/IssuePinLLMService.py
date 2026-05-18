from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai import errors as genai_errors

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException, raise_business_exception

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IssuePinLLMService:
    """커뮤니티 핀 문구용 텍스트 전용 Gemini 호출 (VLM과 모델·역할 분리)."""

    api_key: str
    model_name: str = "gemini-2.0-flash"
    client: genai.Client = field(init=False, repr=False)
    fallback_models: tuple[str, ...] = ("gemini-2.0-flash", "gemini-2.0-flash-lite")

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code in {429, 500, 502, 503, 504}:
            return True
        message = str(exc).lower()
        return ("unavailable" in message) or ("high demand" in message) or ("timed out" in message)

    async def _generate_with_retry(self, *, contents: str):
        model_candidates: list[str] = [self.model_name]
        model_candidates.extend(m for m in self.fallback_models if m != self.model_name)
        last_error: Exception | None = None
        for model in model_candidates:
            for attempt in range(3):
                try:
                    return await self.client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                    )
                except (genai_errors.ServerError, genai_errors.APIError) as exc:
                    last_error = exc
                    if not self._is_retryable_error(exc):
                        raise
                    if attempt == 2:
                        break
                    delay = 0.6 * (2 ** attempt)
                    logger.warning(
                        "Pin model retry: model=%s attempt=%d delay=%.1fs err=%s",
                        model,
                        attempt + 1,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
        if last_error is not None:
            raise last_error
        raise RuntimeError("generate_content 호출에 실패했습니다.")

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
