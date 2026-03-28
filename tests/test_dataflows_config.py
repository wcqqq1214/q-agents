# tests/test_dataflows_config.py
from app.dataflows.config import DEFAULT_CONFIG


def test_default_config_structure():
    """Test default config has required keys"""
    assert "data_vendors" in DEFAULT_CONFIG
    assert "tool_vendors" in DEFAULT_CONFIG
    assert "mcp_servers" in DEFAULT_CONFIG
    assert "redis_url" in DEFAULT_CONFIG


# Note: validate_config() tests will be in Task 7 after interface.py is created
