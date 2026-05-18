from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS_PER_MODEL = 5
DEFAULT_BASE_DELAY_SECONDS = 1.0


def parse_gemini_model_list(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def is_retryable_gemini_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {429, 500, 502, 503, 504}:
        return True
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "unavailable",
            "high demand",
            "timed out",
            "resource exhausted",
            "overloaded",
        )
    )


def should_skip_gemini_model(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {400, 404}:
        return True
    text = str(exc).lower()
    return ("no longer available" in text) or ("not found" in text and "model" in text)


def _format_log_context(log_context: str | None) -> str:
    if not log_context:
        return ""
    return f" [{log_context}]"


async def generate_content_with_retry(
    client: Any,
    *,
    model_name: str,
    contents: Any,
    config: Any | None = None,
    fallback_models: tuple[str, ...] = (),
    max_attempts_per_model: int = DEFAULT_MAX_ATTEMPTS_PER_MODEL,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    log_prefix: str = "Gemini",
    log_context: str | None = None,
) -> Any:
    model_candidates = [model_name]
    model_candidates.extend(m for m in fallback_models if m != model_name)
    last_error: Exception | None = None
    ctx = _format_log_context(log_context)

    logger.info(
        "%s call start%s: primary=%s fallbacks=%s chain=%s max_attempts_per_model=%d",
        log_prefix,
        ctx,
        model_name,
        list(fallback_models),
        model_candidates,
        max_attempts_per_model,
    )

    for model_index, model in enumerate(model_candidates):
        if model_index > 0:
            logger.warning(
                "%s fallback switch%s: model=%s (%d/%d in chain) reason=previous_model_exhausted last_err=%s",
                log_prefix,
                ctx,
                model,
                model_index + 1,
                len(model_candidates),
                last_error,
            )

        for attempt in range(max_attempts_per_model):
            attempt_no = attempt + 1
            logger.info(
                "%s attempt start%s: model=%s attempt=%d/%d",
                log_prefix,
                ctx,
                model,
                attempt_no,
                max_attempts_per_model,
            )
            try:
                kwargs: dict[str, Any] = {"model": model, "contents": contents}
                if config is not None:
                    kwargs["config"] = config
                result = await client.aio.models.generate_content(**kwargs)
                logger.info(
                    "%s success%s: model=%s attempt=%d/%d",
                    log_prefix,
                    ctx,
                    model,
                    attempt_no,
                    max_attempts_per_model,
                )
                return result
            except (genai_errors.ServerError, genai_errors.APIError) as exc:
                last_error = exc
                status_code = getattr(exc, "status_code", None)
                if should_skip_gemini_model(exc):
                    logger.warning(
                        "%s model skip%s: model=%s status=%s err=%s",
                        log_prefix,
                        ctx,
                        model,
                        status_code,
                        exc,
                    )
                    break
                if not is_retryable_gemini_error(exc):
                    logger.error(
                        "%s non-retryable error%s: model=%s attempt=%d/%d status=%s err=%s",
                        log_prefix,
                        ctx,
                        model,
                        attempt_no,
                        max_attempts_per_model,
                        status_code,
                        exc,
                    )
                    raise
                if attempt == max_attempts_per_model - 1:
                    logger.warning(
                        "%s model exhausted%s: model=%s attempts=%d last_err=%s",
                        log_prefix,
                        ctx,
                        model,
                        max_attempts_per_model,
                        exc,
                    )
                    break
                delay = base_delay_seconds * (2**attempt)
                logger.warning(
                    "%s retry scheduled%s: model=%s attempt=%d/%d next_delay=%.1fs status=%s err=%s",
                    log_prefix,
                    ctx,
                    model,
                    attempt_no,
                    max_attempts_per_model,
                    delay,
                    status_code,
                    exc,
                )
                await asyncio.sleep(delay)

    logger.error(
        "%s all models failed%s: chain=%s max_attempts_per_model=%d last_err=%s",
        log_prefix,
        ctx,
        model_candidates,
        max_attempts_per_model,
        last_error,
    )
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{log_prefix} generate_content 호출에 실패했습니다.")
