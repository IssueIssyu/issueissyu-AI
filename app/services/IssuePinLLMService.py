from __future__ import annotations

from dataclasses import dataclass, field

from google import genai

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException, raise_business_exception


@dataclass(slots=True)
class IssuePinLLMService:
    """커뮤니티 핀 문구용 텍스트 전용 Gemini 호출 (VLM과 모델·역할 분리)."""

    api_key: str
    model_name: str = "gemini-2.0-flash"
    client: genai.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    async def generate_pin_text(self, *, prompt: str) -> str:
        """`issue_pin_prompt`로 만든 전체 프롬프트 한 덩어리를 넣고, 핀 본문만 받는다."""
        text = (prompt or "").strip()
        if not text:
            raise_business_exception(ErrorCode.ISSUE_PIN_PROMPT_EMPTY)

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=text,
        )
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
