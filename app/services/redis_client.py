"""Redis client helpers with a local circuit breaker."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from enum import Enum
from typing import Any, Dict, Optional

import redis
import redis.asyncio as redis_async

from app.config_manager import config_manager

logger = logging.getLogger(__name__)

_async_client: Optional[redis_async.Redis] = None
_async_pool: Optional[redis_async.ConnectionPool] = None
_sync_client: Optional[redis.Redis] = None
_sync_pool: Optional[redis.ConnectionPool] = None
_async_lock = asyncio.Lock()
_sync_lock = threading.Lock()


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple local-state circuit breaker for Redis operations."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_successes = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def can_attempt(self) -> bool:
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_successes = 0
                    return True
                return False

            return self._half_open_successes < self.half_open_max_calls

    def record_success(self) -> bool:
        """Record a successful operation.

        Returns:
            True when the breaker transitions back to CLOSED.
        """
        with self._lock:
            previous_state = self._state

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._half_open_successes = 0
            else:
                self._state = CircuitState.CLOSED
                self._failure_count = 0

            return previous_state != CircuitState.CLOSED and self._state == CircuitState.CLOSED

    def record_failure(self) -> bool:
        """Record a failed operation.

        Returns:
            True when the breaker transitions to OPEN.
        """
        with self._lock:
            self._last_failure_time = time.time()
            previous_state = self._state

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._failure_count = self.failure_threshold
                self._half_open_successes = 0
            else:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN

            return previous_state != CircuitState.OPEN and self._state == CircuitState.OPEN

    def reset(self) -> None:
        """Reset breaker state for tests or clean shutdown."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0
            self._half_open_successes = 0


redis_circuit_breaker = CircuitBreaker()


def get_redis_settings() -> Dict[str, Any]:
    """Return Redis settings from the config manager."""
    return config_manager.get_redis_settings()


def is_redis_enabled() -> bool:
    """Return whether Redis is enabled in configuration."""
    return bool(get_redis_settings()["redis_enabled"])


def _build_pool_kwargs(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "max_connections": settings["max_connections"],
        "socket_timeout": settings["socket_timeout"],
        "socket_connect_timeout": settings["socket_connect_timeout"],
        "health_check_interval": settings["health_check_interval"],
    }


async def get_redis_client(force_refresh: bool = False) -> Optional[redis_async.Redis]:
    """Get or create the shared async Redis client."""
    global _async_client, _async_pool

    settings = get_redis_settings()
    if not settings["redis_enabled"]:
        return None

    async with _async_lock:
        if force_refresh:
            await close_redis_client()

        if _async_client is not None:
            return _async_client

        _async_pool = redis_async.ConnectionPool.from_url(
            settings["redis_url"],
            decode_responses=False,
            **_build_pool_kwargs(settings),
        )
        _async_client = redis_async.Redis.from_pool(_async_pool)
        return _async_client


def get_sync_redis_client(force_refresh: bool = False) -> Optional[redis.Redis]:
    """Get or create the shared sync Redis client."""
    global _sync_client, _sync_pool

    settings = get_redis_settings()
    if not settings["redis_enabled"]:
        return None

    with _sync_lock:
        if force_refresh:
            close_sync_redis_client()

        if _sync_client is not None:
            return _sync_client

        _sync_pool = redis.ConnectionPool.from_url(
            settings["redis_url"],
            decode_responses=False,
            **_build_pool_kwargs(settings),
        )
        _sync_client = redis.Redis.from_pool(_sync_pool)
        return _sync_client


async def close_redis_client() -> None:
    """Close the shared async Redis client."""
    global _async_client, _async_pool

    client = _async_client
    pool = _async_pool
    _async_client = None
    _async_pool = None

    if client is not None:
        close_result = client.aclose(close_connection_pool=True)
        if inspect.isawaitable(close_result):
            await close_result
    elif pool is not None:
        close_result = pool.aclose()
        if inspect.isawaitable(close_result):
            await close_result


def close_sync_redis_client() -> None:
    """Close the shared sync Redis client."""
    global _sync_client, _sync_pool

    client = _sync_client
    pool = _sync_pool
    _sync_client = None
    _sync_pool = None

    if client is not None:
        client.close()
    if pool is not None:
        pool.disconnect()


async def ping_redis() -> bool:
    """Ping Redis and update the circuit breaker state."""
    if not redis_circuit_breaker.can_attempt():
        return False

    client = await get_redis_client()
    if client is None:
        return False

    try:
        await client.ping()
        redis_circuit_breaker.record_success()
        return True
    except redis.RedisError as exc:
        redis_circuit_breaker.record_failure()
        logger.warning("Redis ping failed, circuit breaker updated: %s", exc)
        return False


async def reset_redis_state() -> None:
    """Reset shared Redis clients and circuit breaker state."""
    close_sync_redis_client()
    await close_redis_client()
    redis_circuit_breaker.reset()
