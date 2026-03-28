"""Tests for crypto quotes routes."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.okx.exceptions import OKXAuthError, OKXError, OKXRateLimitError


@pytest.fixture
def client():
    """Create test client."""
    from app.api.main import app

    return TestClient(app)


@pytest.fixture
def mock_okx_client():
    """Create mock OKX client."""
    mock = Mock()
    mock.get_ticker = AsyncMock()
    return mock


class TestCryptoQuotesRoute:
    """Tests for GET /api/crypto/quotes endpoint."""

    def test_get_crypto_quotes_success(self, client, mock_okx_client):
        """Test successful quotes retrieval for BTC-USDT,ETH-USDT."""
        # Mock BTC ticker
        mock_okx_client.get_ticker.side_effect = [
            {
                "instId": "BTC-USDT",
                "last": "50000.5",
                "sodUtc8": "49000.0",  # Today's open price (UTC+8 00:00)
                "open24h": "48500.0",
                "high24h": "51000.0",
                "low24h": "48500.0",
                "vol24h": "12345.67",
            },
            {
                "instId": "ETH-USDT",
                "last": "3000.25",
                "sodUtc8": "2950.0",  # Today's open price (UTC+8 00:00)
                "open24h": "2900.0",
                "high24h": "3050.0",
                "low24h": "2900.0",
                "vol24h": "54321.12",
            },
        ]

        with patch("app.api.routes.crypto.get_okx_client", return_value=mock_okx_client):
            response = client.get("/api/crypto/quotes?symbols=BTC-USDT,ETH-USDT")

        assert response.status_code == 200
        data = response.json()
        assert len(data["quotes"]) == 2

        # Check BTC quote
        btc_quote = data["quotes"][0]
        assert btc_quote["symbol"] == "BTC-USDT"
        assert btc_quote["name"] == "Bitcoin"
        assert btc_quote["price"] == 50000.5
        assert btc_quote["high24h"] == 51000.0
        assert btc_quote["low24h"] == 48500.0
        assert btc_quote["volume24h"] == 12345.67
        # Change amount: 50000.5 - 49000.0 = 1000.5
        assert abs(btc_quote["change"] - 1000.5) < 0.01
        # Change percentage: (50000.5 - 49000.0) / 49000.0 * 100 = 2.04%
        assert abs(btc_quote["changePercent"] - 2.04) < 0.01

        # Check ETH quote
        eth_quote = data["quotes"][1]
        assert eth_quote["symbol"] == "ETH-USDT"
        assert eth_quote["name"] == "Ethereum"
        assert eth_quote["price"] == 3000.25

    def test_get_crypto_quotes_missing_symbols(self, client):
        """Test validation error when symbols parameter missing."""
        response = client.get("/api/crypto/quotes")

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_get_crypto_quotes_auth_error(self, client, mock_okx_client):
        """Test quotes route with authentication error."""
        mock_okx_client.get_ticker.side_effect = OKXAuthError("Invalid API key", code="50113")

        with patch("app.api.routes.crypto.get_okx_client", return_value=mock_okx_client):
            response = client.get("/api/crypto/quotes?symbols=BTC-USDT")

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "Invalid API key" in data["detail"]

    def test_get_crypto_quotes_rate_limit_error(self, client, mock_okx_client):
        """Test quotes route with rate limit error."""
        mock_okx_client.get_ticker.side_effect = OKXRateLimitError(
            "Rate limit exceeded", code="50011"
        )

        with patch("app.api.routes.crypto.get_okx_client", return_value=mock_okx_client):
            response = client.get("/api/crypto/quotes?symbols=BTC-USDT")

        assert response.status_code == 429
        data = response.json()
        assert "detail" in data
        assert "Rate limit exceeded" in data["detail"]

    def test_get_crypto_quotes_okx_error(self, client, mock_okx_client):
        """Test quotes route with generic OKX error."""
        mock_okx_client.get_ticker.side_effect = OKXError("API error")

        with patch("app.api.routes.crypto.get_okx_client", return_value=mock_okx_client):
            response = client.get("/api/crypto/quotes?symbols=BTC-USDT")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_get_crypto_quotes_unexpected_error(self, client, mock_okx_client):
        """Test quotes route with unexpected error."""
        mock_okx_client.get_ticker.side_effect = Exception("Unexpected error")

        with patch("app.api.routes.crypto.get_okx_client", return_value=mock_okx_client):
            response = client.get("/api/crypto/quotes?symbols=BTC-USDT")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data


class TestCryptoOHLCRoute:
    """Tests for GET /api/stocks/{symbol}/ohlc endpoint with crypto symbols."""

    def test_get_crypto_ohlc_success(self, client):
        """Test successful OHLC retrieval for BTC-USDT with 1h interval."""
        response = client.get("/api/stocks/BTC-USDT/ohlc?interval=1h")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC-USDT"
        assert "data" in data
        assert isinstance(data["data"], list)
        # Should have data if database was populated in Task 5
        if len(data["data"]) > 0:
            record = data["data"][0]
            assert "date" in record
            assert "open" in record
            assert "high" in record
            assert "low" in record
            assert "close" in record
            assert "volume" in record

    def test_get_stock_ohlc_still_works(self, client):
        """Test that stock OHLC still works for AAPL with day interval."""
        response = client.get("/api/stocks/AAPL/ohlc?interval=day")

        # Should return 200 if AAPL data exists, or 404 if not
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["symbol"] == "AAPL"
            assert "data" in data

    def test_get_crypto_ohlc_invalid_interval(self, client):
        """Test that invalid interval returns 400 error."""
        response = client.get("/api/stocks/BTC-USDT/ohlc?interval=invalid")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Invalid interval" in data["detail"]
