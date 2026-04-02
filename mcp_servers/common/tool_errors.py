"""Friendly tool error formatting for MCP servers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

RATE_LIMIT_HINT_SECONDS = 10


def build_tool_error_payload(
    *,
    provider_name: str,
    tool_name: str,
    exc: Exception,
    base_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a natural-language-friendly tool error payload."""

    lower = str(exc).lower()
    retryable = _is_retryable(lower)
    retry_after_seconds = RATE_LIMIT_HINT_SECONDS if _is_rate_limit(lower) else None
    message = _build_message(
        provider_name=provider_name,
        tool_name=tool_name,
        exc=exc,
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
    )

    payload = dict(base_payload or {})
    payload.update(
        {
            "error": message,
            "error_type": type(exc).__name__,
            "retryable": retryable,
            "retry_after_seconds": retry_after_seconds,
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
    )
    return payload


def _build_message(
    *,
    provider_name: str,
    tool_name: str,
    exc: Exception,
    retryable: bool,
    retry_after_seconds: int | None,
) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    if retry_after_seconds:
        return (
            f"{provider_name} rate limit exceeded while running {tool_name}. "
            f"Wait about {retry_after_seconds} seconds and retry. "
            f"Original error: {detail}"
        )
    if retryable:
        return (
            f"{provider_name} was temporarily unavailable while running {tool_name}. "
            "Retry in a few seconds. "
            f"Original error: {detail}"
        )
    return f"{provider_name} failed while running {tool_name}. Original error: {detail}"


def _is_rate_limit(message: str) -> bool:
    return any(
        token in message for token in ("rate limit", "too many requests", "429", "quota exceeded")
    )


def _is_retryable(message: str) -> bool:
    if _is_rate_limit(message):
        return True
    return any(
        token in message
        for token in (
            "temporarily unavailable",
            "timed out",
            "timeout",
            "connection reset",
            "connection refused",
            "service unavailable",
            "bad gateway",
            "gateway timeout",
            "network",
        )
    )
