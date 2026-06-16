from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from google.genai import errors as genai_errors

if TYPE_CHECKING:
    from app.services.internal.ai.gemini_key_pool import GeminiKeyPool

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


async def _generate_once(
    client: Any,
    *,
    model: str,
    contents: Any,
    config: Any | None,
) -> Any:
    kwargs: dict[str, Any] = {"model": model, "contents": contents}
    if config is not None:
        kwargs["config"] = config
    return await client.aio.models.generate_content(**kwargs)


async def _generate_with_key_failover(
    *,
    key_pool: GeminiKeyPool,
    start_index: int,
    start_client: Any,
    model: str,
    contents: Any,
    config: Any | None,
    log_prefix: str,
    ctx: str,
    attempt_no: int,
    max_attempts_per_model: int,
) -> Any:
    clients_to_try: list[tuple[int, Any]] = [(start_index, start_client)]
    for failover_idx in key_pool.failover_indices(start_index):
        clients_to_try.append((failover_idx, key_pool.client_at(failover_idx)))

    last_error: Exception | None = None
    for key_idx, try_client in clients_to_try:
        try:
            result = await _generate_once(
                try_client,
                model=model,
                contents=contents,
                config=config,
            )
            if key_idx != start_index:
                logger.warning(
                    "%s key failover success%s: model=%s key_index=%d/%d attempt=%d/%d",
                    log_prefix,
                    ctx,
                    model,
                    key_idx + 1,
                    key_pool.size,
                    attempt_no,
                    max_attempts_per_model,
                )
            return result
        except (genai_errors.ServerError, genai_errors.APIError) as exc:
            last_error = exc
            if key_idx != clients_to_try[-1][0]:
                logger.warning(
                    "%s key failover retry%s: model=%s key_index=%d/%d status=%s err=%s",
                    log_prefix,
                    ctx,
                    model,
                    key_idx + 1,
                    key_pool.size,
                    getattr(exc, "status_code", None),
                    exc,
                )
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{log_prefix} generate_content 호출에 실패했습니다.")


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
    key_pool: GeminiKeyPool | None = None,
) -> Any:
    model_candidates = [model_name]
    model_candidates.extend(m for m in fallback_models if m != model_name)
    last_error: Exception | None = None
    ctx = _format_log_context(log_context)
    pool_active = key_pool is not None and key_pool.enabled

    logger.info(
        "%s call start%s: primary=%s fallbacks=%s chain=%s max_attempts_per_model=%d key_pool=%s",
        log_prefix,
        ctx,
        model_name,
        list(fallback_models),
        model_candidates,
        max_attempts_per_model,
        f"{key_pool.size}keys" if pool_active else "off",
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
            active_client = client
            key_index: int | None = None
            if pool_active and key_pool is not None:
                key_index, _, active_client = await key_pool.acquire()
                logger.info(
                    "%s attempt start%s: model=%s attempt=%d/%d key_index=%d/%d",
                    log_prefix,
                    ctx,
                    model,
                    attempt_no,
                    max_attempts_per_model,
                    key_index + 1,
                    key_pool.size,
                )
            else:
                logger.info(
                    "%s attempt start%s: model=%s attempt=%d/%d",
                    log_prefix,
                    ctx,
                    model,
                    attempt_no,
                    max_attempts_per_model,
                )
            try:
                if pool_active and key_pool is not None and key_index is not None:
                    result = await _generate_with_key_failover(
                        key_pool=key_pool,
                        start_index=key_index,
                        start_client=active_client,
                        model=model,
                        contents=contents,
                        config=config,
                        log_prefix=log_prefix,
                        ctx=ctx,
                        attempt_no=attempt_no,
                        max_attempts_per_model=max_attempts_per_model,
                    )
                else:
                    result = await _generate_once(
                        active_client,
                        model=model,
                        contents=contents,
                        config=config,
                    )
                logger.info(
                    "%s success%s: model=%s attempt=%d/%d%s",
                    log_prefix,
                    ctx,
                    model,
                    attempt_no,
                    max_attempts_per_model,
                    f" key_index={key_index + 1}/{key_pool.size}" if pool_active and key_index is not None and key_pool else "",
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
