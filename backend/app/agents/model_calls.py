"""Bounded retry wrapper for model calls used inside analysis nodes."""

import asyncio
from typing import Any

import httpx
import openai
import structlog

log = structlog.get_logger(__name__)

MODEL_CALL_ATTEMPTS = 2
MODEL_CALL_TIMEOUT_SECONDS = 30
MODEL_CALL_RETRY_DELAY_SECONDS = 0.25

TRANSIENT_MODEL_ERRORS = (
    TimeoutError,
    httpx.TimeoutException,
    httpx.TransportError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)


async def run_model_with_retry(
    agent: Any,
    prompt: str,
    *,
    operation: str,
) -> Any:
    """Run a PydanticAI agent with bounded transient-error retry."""
    last_error: BaseException | None = None
    for attempt in range(1, MODEL_CALL_ATTEMPTS + 1):
        try:
            return await asyncio.wait_for(
                agent.run(prompt),
                timeout=MODEL_CALL_TIMEOUT_SECONDS,
            )
        except TRANSIENT_MODEL_ERRORS as exc:
            last_error = exc
            if attempt >= MODEL_CALL_ATTEMPTS:
                break
            log.warning(
                "model_call_retrying",
                operation=operation,
                attempt=attempt,
                max_attempts=MODEL_CALL_ATTEMPTS,
                error_type=exc.__class__.__name__,
                retry_delay_seconds=MODEL_CALL_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(MODEL_CALL_RETRY_DELAY_SECONDS)
    if last_error is not None:
        raise last_error
    raise RuntimeError("model call retry loop exited without result or error")
