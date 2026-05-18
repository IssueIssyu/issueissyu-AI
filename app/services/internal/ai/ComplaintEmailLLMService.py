from __future__ import annotations

import re
from dataclasses import dataclass, field

from google import genai

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException, raise_business_exception
from app.schemas.ComplaintEmailDTO import ComplaintEmailLlmBundle
from app.services.prompts.complaint_email_notification import complaint_notification_prompt
from app.services.prompts.complaint_email_opinion import complaint_opinion_prompt


_HTML_FENCE_RE = re.compile(r"^```(?:html)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


@dataclass(slots=True)
class ComplaintEmailLLMService:
    api_key: str
    model_name: str = "gemini-2.5-flash"
    client: genai.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    async def generate_opinion_html(self, bundle: ComplaintEmailLlmBundle) -> str:
        prompt = complaint_opinion_prompt(bundle)
        raw = await self._generate_text(prompt)
        return self._normalize_html_response(raw)

    async def generate_notification_email(
        self,
        *,
        pin_title: str,
        pin_content: str,
        opinion_summary: str,
        reliability_score: float,
        validity: bool,
        risk_note: str | None,
    ) -> str:
        prompt = complaint_notification_prompt(
            pin_title=pin_title,
            pin_content=pin_content,
            opinion_summary=opinion_summary,
            reliability_score=reliability_score,
            validity=validity,
            risk_note=risk_note,
        )
        return await self._generate_text(prompt)

    async def _generate_text(self, prompt: str) -> str:
        text = (prompt or "").strip()
        if not text:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, "LLM 프롬프트가 비어 있습니다.")

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

    @staticmethod
    def _normalize_html_response(text: str) -> str:
        cleaned = _HTML_FENCE_RE.sub("", text.strip())
        if "<html" not in cleaned.lower():
            return f"<!DOCTYPE html><html><head><meta charset=\"utf-8\"/></head><body>{cleaned}</body></html>"
        return cleaned
