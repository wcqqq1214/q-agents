"""Distributed rate limiter with Redis-first fallback."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
import uuid
from collections import deque
from functools import wraps
from typing import Any, Callable, Dict, Optional

import redis

from app.config.rate_limits import RATE_LIMITS, get_fallback_rate_limits
from app.services.redis_client import (
    get_redis_client,
    get_sync_redis_client,
    is_redis_enabled,
    redis_circuit_breaker,
)

logger = logging.getLogger(__name__)

ACQUIRE_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local request_id = ARGV[4]
local window_start = now - window_ms

redis.call('ZREMRANGEBYSCORE', key, 0, window_start)

local count = redis.call('ZCARD', key)
if count < max_requests then
    redis.call('ZADD', key, now, request_id)
    redis.call('PEXPIRE', key, window_ms)
    return 1
end

return 0
"""

COUNT_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local window_start = now - window_ms

redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
return redis.call('ZCARD', key)
"""

RECORD_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local request_id = ARGV[3]

redis.call('ZADD', key, now, request_id)
redis.call('PEXPIRE', key, window_ms)
return 1
"""


class RateLimitExceeded(RuntimeError):
    """Raised when an upstream request would exceed its rate limit."""


class LocalRateLimiter:
    """Local sliding-window rate limiter used when Redis is unavailable."""

    def __init__(self, max_requests: int, window: int) -> None:
        self.max_requests = max_requests
        self.window = window
        self.requests: deque[float] = deque()
        self.lock = threading.Lock()

    def _prune(self, now: float) -> None:
        while self.requests and self.requests[0] <= now - self.window:
            self.requests.popleft()

    def is_allowed(self) -> bool:
        with self.lock:
            now = time.time()
            self._prune(now)
            if len(self.requests) >= self.max_requests:
                return False
            self.requests.append(now)
            return True

    def can_accept(self) -> bool:
        with self.lock:
            now = time.time()
            self._prune(now)
            return len(self.requests) < self.max_requests

    def record(self) -> None:
        with self.lock:
            now = time.time()
            self._prune(now)
            self.requests.append(now)


_local_limiters: Dict[str, LocalRateLimiter] = {}
_local_limiters_lock = threading.Lock()


def _rate_limit_key(exchange: str, identifier: str) -> str:
    return f"ratelimit:{exchange}:{identifier}"


def _get_exchange_limit(exchange: str) -> Dict[str, int]:
    try:
        return RATE_LIMITS[exchange]
    except KeyError as exc:
        raise ValueError(f"Unsupported exchange for rate limiter: {exchange}") from exc


def _get_fallback_limiter(exchange: str, identifier: str) -> LocalRateLimiter:
    fallback_limits = get_fallback_rate_limits()
    config = fallback_limits[exchange]
    key = f"{exchange}:{identifier}"

    with _local_limiters_lock:
        limiter = _local_limiters.get(key)
        if limiter is None:
            limiter = LocalRateLimiter(
                max_requests=config["max_requests"],
                window=config["window"],
            )
            _local_limiters[key] = limiter
        return limiter


def _resolve_identifier(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: Dict[str, Any],
    identifier_key: Optional[str],
) -> str:
    if not identifier_key:
        return "global"

    bound = inspect.signature(func).bind_partial(*args, **kwargs)
    value: Any = bound.arguments

    for part in identifier_key.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
        if value is None:
            return "global"

    return str(value)


async def _redis_acquire(exchange: str, identifier: str) -> bool:
    config = _get_exchange_limit(exchange)
    client = await get_redis_client()
    if client is None:
        return False

    now_ms = int(time.time() * 1000)
    key = _rate_limit_key(exchange, identifier)
    allowed = await client.eval(
        ACQUIRE_LUA_SCRIPT,
        1,
        key,
        now_ms,
        config["window"] * 1000,
        config["max_requests"],
        uuid.uuid4().hex,
    )
    return bool(allowed)


def _redis_acquire_sync(exchange: str, identifier: str) -> bool:
    config = _get_exchange_limit(exchange)
    client = get_sync_redis_client()
    if client is None:
        return False

    now_ms = int(time.time() * 1000)
    key = _rate_limit_key(exchange, identifier)
    allowed = client.eval(
        ACQUIRE_LUA_SCRIPT,
        1,
        key,
        now_ms,
        config["window"] * 1000,
        config["max_requests"],
        uuid.uuid4().hex,
    )
    return bool(allowed)


async def acquire_rate_limit(exchange: str, identifier: str = "global") -> bool:
    """Atomically check and record a request."""
    if is_redis_enabled() and redis_circuit_breaker.can_attempt():
        try:
            allowed = await _redis_acquire(exchange, identifier)
            redis_circuit_breaker.record_success()
            return allowed
        except (redis.RedisError, asyncio.TimeoutError, OSError) as exc:
            redis_circuit_breaker.record_failure()
            logger.warning("Redis rate limiter degraded to local mode: %s", exc)

    return _get_fallback_limiter(exchange, identifier).is_allowed()


def acquire_rate_limit_sync(exchange: str, identifier: str = "global") -> bool:
    """Sync variant of acquire_rate_limit for synchronous clients."""
    if is_redis_enabled() and redis_circuit_breaker.can_attempt():
        try:
            allowed = _redis_acquire_sync(exchange, identifier)
            redis_circuit_breaker.record_success()
            return allowed
        except (redis.RedisError, OSError) as exc:
            redis_circuit_breaker.record_failure()
            logger.warning("Redis rate limiter degraded to local mode: %s", exc)

    return _get_fallback_limiter(exchange, identifier).is_allowed()


async def check_rate_limit(exchange: str, identifier: str = "global") -> bool:
    """Check whether a request can proceed without recording it."""
    config = _get_exchange_limit(exchange)
    if is_redis_enabled() and redis_circuit_breaker.can_attempt():
        try:
            client = await get_redis_client()
            if client is None:
                return True
            count = await client.eval(
                COUNT_LUA_SCRIPT,
                1,
                _rate_limit_key(exchange, identifier),
                int(time.time() * 1000),
                config["window"] * 1000,
            )
            redis_circuit_breaker.record_success()
            return int(count) < config["max_requests"]
        except (redis.RedisError, asyncio.TimeoutError, OSError) as exc:
            redis_circuit_breaker.record_failure()
            logger.warning("Redis rate-limit check degraded to local mode: %s", exc)

    return _get_fallback_limiter(exchange, identifier).can_accept()


async def record_request(exchange: str, identifier: str = "global") -> None:
    """Record a request without checking the current quota."""
    config = _get_exchange_limit(exchange)
    if is_redis_enabled() and redis_circuit_breaker.can_attempt():
        try:
            client = await get_redis_client()
            if client is not None:
                await client.eval(
                    RECORD_LUA_SCRIPT,
                    1,
                    _rate_limit_key(exchange, identifier),
                    int(time.time() * 1000),
                    config["window"] * 1000,
                    uuid.uuid4().hex,
                )
                redis_circuit_breaker.record_success()
                return
        except (redis.RedisError, asyncio.TimeoutError, OSError) as exc:
            redis_circuit_breaker.record_failure()
            logger.warning("Redis request recording degraded to local mode: %s", exc)

    _get_fallback_limiter(exchange, identifier).record()


def rate_limit(
    exchange: str,
    identifier_key: Optional[str] = None,
    per_function: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate sync or async functions with Redis-backed rate limiting."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                identifier = _resolve_identifier(func, args, kwargs, identifier_key)
                if per_function:
                    identifier = f"{identifier}:{func.__name__}"
                allowed = await acquire_rate_limit(exchange, identifier)
                if not allowed:
                    raise RateLimitExceeded(
                        f"Rate limit exceeded for {exchange} ({identifier})"
                    )
                return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            identifier = _resolve_identifier(func, args, kwargs, identifier_key)
            if per_function:
                identifier = f"{identifier}:{func.__name__}"
            allowed = acquire_rate_limit_sync(exchange, identifier)
            if not allowed:
                raise RateLimitExceeded(
                    f"Rate limit exceeded for {exchange} ({identifier})"
                )
            return func(*args, **kwargs)

        return sync_wrapper

    return decorator


def reset_local_rate_limiters() -> None:
    """Clear local fallback limiter state for tests."""
    with _local_limiters_lock:
        _local_limiters.clear()
