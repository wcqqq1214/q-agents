"""Tests for Redis client helpers and circuit breaker behaviour."""

import asyncio
from unittest.mock import Mock, patch

import pytest

from app.services.redis_client import (
    CircuitBreaker,
    CircuitState,
    get_redis_client,
    get_sync_redis_client,
    reset_redis_state,
)


@pytest.fixture(autouse=True)
def reset_clients(monkeypatch):
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    asyncio.run(reset_redis_state())
    yield
    asyncio.run(reset_redis_state())


def test_circuit_breaker_state_transitions():
    """Circuit breaker should open after repeated failures and recover."""
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0, half_open_max_calls=1)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.can_attempt() is True

    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED

    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.can_attempt() is True
    assert breaker.state == CircuitState.HALF_OPEN

    recovered = breaker.record_success()
    assert recovered is True
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_get_redis_client_builds_async_client():
    """Async Redis client should be created from configured settings."""
    mock_pool = Mock()
    mock_client = Mock()

    with patch("app.services.redis_client.redis_async.ConnectionPool.from_url", return_value=mock_pool) as mock_from_url:
        with patch("app.services.redis_client.redis_async.Redis.from_pool", return_value=mock_client) as mock_from_pool:
            client = await get_redis_client()

    assert client is mock_client
    mock_from_url.assert_called_once()
    mock_from_pool.assert_called_once_with(mock_pool)


def test_get_sync_redis_client_builds_sync_client():
    """Sync Redis client should be created from configured settings."""
    mock_pool = Mock()
    mock_client = Mock()

    with patch("app.services.redis_client.redis.ConnectionPool.from_url", return_value=mock_pool) as mock_from_url:
        with patch("app.services.redis_client.redis.Redis.from_pool", return_value=mock_client) as mock_from_pool:
            client = get_sync_redis_client()

    assert client is mock_client
    mock_from_url.assert_called_once()
    mock_from_pool.assert_called_once_with(mock_pool)
