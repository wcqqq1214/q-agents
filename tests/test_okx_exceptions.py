"""测试OKX错误类型"""

from app.okx.exceptions import (
    OKXAuthError,
    OKXConfigError,
    OKXError,
    OKXInsufficientBalanceError,
    OKXOrderError,
    OKXRateLimitError,
)


def test_okx_error_basic():
    """测试基础错误"""
    error = OKXError("Test error")
    assert str(error) == "Test error"
    assert error.message == "Test error"
    assert error.code is None


def test_okx_error_with_code():
    """测试带错误码的错误"""
    error = OKXError("Test error", code="50000")
    assert str(error) == "[50000] Test error"
    assert error.code == "50000"


def test_okx_auth_error():
    """测试认证错误"""
    error = OKXAuthError("Invalid API key", code="50101")
    assert isinstance(error, OKXError)
    assert str(error) == "[50101] Invalid API key"


def test_okx_rate_limit_error():
    """测试频率限制错误"""
    error = OKXRateLimitError("Rate limit exceeded")
    assert isinstance(error, OKXError)


def test_okx_insufficient_balance_error():
    """测试余额不足错误"""
    error = OKXInsufficientBalanceError("Insufficient balance")
    assert isinstance(error, OKXError)


def test_okx_order_error():
    """测试订单错误"""
    error = OKXOrderError("Order failed")
    assert isinstance(error, OKXError)


def test_okx_config_error():
    """测试配置错误"""
    error = OKXConfigError("Missing API key")
    assert isinstance(error, OKXError)
