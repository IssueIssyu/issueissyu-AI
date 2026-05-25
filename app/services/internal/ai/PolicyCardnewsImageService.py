from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.internal.ai.gemini_retry import (
    is_retryable_gemini_error,
    parse_gemini_model_list,
    should_skip_gemini_model,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS_PER_MODEL = 3
DEFAULT_BASE_DELAY_SECONDS = 2.0


@dataclass(slots=True)
class PolicyCardnewsImageService:
    # 정책 카드뉴스 슬라이드 이미지 생성 (텍스트 모델과 분리)
    api_key: str
    model_name: str = "gemini-2.5-flash-image"
    client: genai.Client = field(init=False, repr=False)
    fallback_models: tuple[str, ...] = ("gemini-3-pro-image-preview",)

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    @classmethod
    def from_settings(cls) -> PolicyCardnewsImageService:
        secret = settings.gemini_api_key
        if secret is None:
            raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")
        fallbacks = parse_gemini_model_list(settings.gemini_cardnews_image_fallback_models)
        return cls(
            api_key=secret.get_secret_value(),
            model_name=settings.gemini_cardnews_image_model.strip(),
            fallback_models=fallbacks,
        )

    async def generate_slide_image_bytes(self, *, prompt: str) -> bytes:
        text = (prompt or "").strip()
        if not text:
            raise ValueError("카드뉴스 이미지 프롬프트가 비어 있음")

        model_candidates = [self.model_name]
        model_candidates.extend(m for m in self.fallback_models if m != self.model_name)
        last_error: Exception | None = None

        for model_index, model in enumerate(model_candidates):
            if model_index > 0:
                logger.warning(
                    "CardnewsImage fallback switch: model=%s (%d/%d)",
                    model,
                    model_index + 1,
                    len(model_candidates),
                )

            for attempt in range(1, DEFAULT_MAX_ATTEMPTS_PER_MODEL + 1):
                try:
                    if model.lower().startswith("imagen"):
                        return await self._generate_with_imagen(model=model, prompt=text)
                    return await self._generate_with_gemini_image(model=model, prompt=text)
                except Exception as exc:
                    last_error = exc
                    if should_skip_gemini_model(exc):
                        logger.warning(
                            "CardnewsImage skip model=%s err=%s",
                            model,
                            exc,
                        )
                        break
                    if attempt >= DEFAULT_MAX_ATTEMPTS_PER_MODEL or not is_retryable_gemini_error(exc):
                        break
                    delay = DEFAULT_BASE_DELAY_SECONDS * attempt
                    logger.warning(
                        "CardnewsImage retry model=%s attempt=%d/%d delay=%.1fs err=%s",
                        model,
                        attempt,
                        DEFAULT_MAX_ATTEMPTS_PER_MODEL,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"카드뉴스 이미지 생성 실패 (models={model_candidates}): {last_error}",
        ) from last_error

    async def _generate_with_gemini_image(self, *, model: str, prompt: str) -> bytes:
        response = await self.client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.IMAGE],
            ),
        )
        return self._extract_image_bytes(response)

    async def _generate_with_imagen(self, *, model: str, prompt: str) -> bytes:
        response = await self.client.aio.models.generate_images(
            model=model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="3:4",
                output_mime_type="image/png",
            ),
        )
        generated = response.generated_images or []
        if not generated:
            raise RuntimeError("Imagen 응답에 generated_images가 없음")
        data = generated[0].image.image_bytes
        if not data:
            raise RuntimeError("Imagen image_bytes가 비어 있음")
        if isinstance(data, str):
            import base64

            return base64.b64decode(data)
        return bytes(data)

    @staticmethod
    def _extract_image_bytes(response: object) -> bytes:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            raise RuntimeError("이미지 생성 응답 candidates가 없음")

        content = candidates[0].content
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is None or not inline.data:
                continue
            data = inline.data
            if isinstance(data, str):
                import base64

                return base64.b64decode(data)
            return bytes(data)

        raise RuntimeError("이미지 생성 응답에 inline_data가 없음")
