"""Pytest configuration for finance-agent tests."""

import sys
from pathlib import Path

import pytest

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def disable_redis_by_default(monkeypatch):
    """Default test mode uses local fallbacks unless a test opts into Redis."""
    monkeypatch.setenv("REDIS_ENABLED", "false")
