"""Tests for OKX account management routes."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.okx.exceptions import (
    OKXAuthError,
    OKXRateLimitError,
    OKXConfigError,
    OKXError
)


@pytest.fixture
def client():
    """Create test client."""
    from app.api.main import app
    return TestClient(app)


@pytest.fixture
def mock_okx_client():
    """Create mock OKX client."""
    mock = Mock()
    mock.get_account_balance = AsyncMock()
    mock.get_positions = AsyncMock()
    return mock


class TestAccountBalanceRoute:
    """Tests for GET /api/okx/account/balance endpoint."""

    def test_get_balance_all_currencies_demo(self, client, mock_okx_client):
        """Test getting all currencies balance in demo mode."""
        mock_okx_client.get_account_balance.return_value = [
            {'currency': 'USDT', 'available': '1000', 'frozen': '100', 'total': '1100'},
            {'currency': 'BTC', 'available': '0.5', 'frozen': '0', 'total': '0.5'}
        ]

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/balance")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'demo'
        assert len(data['balances']) == 2
        assert data['balances'][0]['currency'] == 'USDT'
        assert data['balances'][1]['currency'] == 'BTC'
        mock_okx_client.get_account_balance.assert_called_once_with(currency=None)

    def test_get_balance_single_currency(self, client, mock_okx_client):
        """Test getting single currency balance."""
        mock_okx_client.get_account_balance.return_value = [
            {'currency': 'USDT', 'available': '1000', 'frozen': '100', 'total': '1100'}
        ]

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/balance?currency=USDT")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'demo'
        assert len(data['balances']) == 1
        assert data['balances'][0]['currency'] == 'USDT'
        mock_okx_client.get_account_balance.assert_called_once_with(currency='USDT')

    def test_get_balance_live_mode(self, client, mock_okx_client):
        """Test getting balance in live mode."""
        mock_okx_client.get_account_balance.return_value = []

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/balance?mode=live")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'live'
        assert data['balances'] == []

    def test_get_balance_auth_error(self, client, mock_okx_client):
        """Test balance route with authentication error."""
        mock_okx_client.get_account_balance.side_effect = OKXAuthError(
            "Invalid API key", code="50113"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/balance")

        assert response.status_code == 401
        data = response.json()
        assert 'detail' in data
        assert 'Invalid API key' in data['detail']

    def test_get_balance_rate_limit_error(self, client, mock_okx_client):
        """Test balance route with rate limit error."""
        mock_okx_client.get_account_balance.side_effect = OKXRateLimitError(
            "Rate limit exceeded", code="50011"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/balance")

        assert response.status_code == 429
        data = response.json()
        assert 'detail' in data
        assert 'Rate limit exceeded' in data['detail']

    def test_get_balance_config_error(self, client):
        """Test balance route with config error."""
        with patch('app.api.routes.okx.get_okx_client', side_effect=OKXConfigError("Missing API key")):
            response = client.get("/api/okx/account/balance")

        assert response.status_code == 400
        data = response.json()
        assert 'detail' in data
        assert 'Missing API key' in data['detail']

    def test_get_balance_invalid_mode(self, client):
        """Test balance route with invalid mode."""
        with patch('app.api.routes.okx.get_okx_client', side_effect=OKXConfigError("Invalid mode: invalid")):
            response = client.get("/api/okx/account/balance?mode=invalid")

        assert response.status_code == 400

    def test_get_balance_generic_error(self, client, mock_okx_client):
        """Test balance route with generic OKX error."""
        mock_okx_client.get_account_balance.side_effect = OKXError("Unknown error")

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/balance")

        assert response.status_code == 400
        data = response.json()
        assert 'detail' in data

    def test_get_balance_unexpected_error(self, client, mock_okx_client):
        """Test balance route with unexpected error."""
        mock_okx_client.get_account_balance.side_effect = Exception("Unexpected error")

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/balance")

        assert response.status_code == 500
        data = response.json()
        assert 'detail' in data


class TestAccountPositionsRoute:
    """Tests for GET /api/okx/account/positions endpoint."""

    def test_get_positions_all(self, client, mock_okx_client):
        """Test getting all positions."""
        mock_okx_client.get_positions.return_value = [
            {
                'instId': 'BTC-USDT-SWAP',
                'instType': 'SWAP',
                'pos': '10',
                'avgPx': '50000',
                'upl': '100'
            }
        ]

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/positions")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'demo'
        assert len(data['positions']) == 1
        assert data['positions'][0]['instId'] == 'BTC-USDT-SWAP'
        mock_okx_client.get_positions.assert_called_once_with(inst_type=None)

    def test_get_positions_by_inst_type(self, client, mock_okx_client):
        """Test getting positions by instrument type."""
        mock_okx_client.get_positions.return_value = [
            {'instId': 'BTC-USDT-SWAP', 'instType': 'SWAP', 'pos': '10'}
        ]

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/positions?inst_type=SWAP")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'demo'
        assert len(data['positions']) == 1
        mock_okx_client.get_positions.assert_called_once_with(inst_type='SWAP')

    def test_get_positions_live_mode(self, client, mock_okx_client):
        """Test getting positions in live mode."""
        mock_okx_client.get_positions.return_value = []

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/positions?mode=live")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'live'
        assert data['positions'] == []

    def test_get_positions_empty(self, client, mock_okx_client):
        """Test getting positions when none exist."""
        mock_okx_client.get_positions.return_value = []

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/positions")

        assert response.status_code == 200
        data = response.json()
        assert data['positions'] == []

    def test_get_positions_auth_error(self, client, mock_okx_client):
        """Test positions route with authentication error."""
        mock_okx_client.get_positions.side_effect = OKXAuthError(
            "Invalid signature", code="50113"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/positions")

        assert response.status_code == 401
        data = response.json()
        assert 'detail' in data

    def test_get_positions_rate_limit_error(self, client, mock_okx_client):
        """Test positions route with rate limit error."""
        mock_okx_client.get_positions.side_effect = OKXRateLimitError(
            "Too many requests", code="50011"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/positions")

        assert response.status_code == 429

    def test_get_positions_config_error(self, client):
        """Test positions route with config error."""
        with patch('app.api.routes.okx.get_okx_client', side_effect=OKXConfigError("Missing config")):
            response = client.get("/api/okx/account/positions")

        assert response.status_code == 400

    def test_get_positions_generic_error(self, client, mock_okx_client):
        """Test positions route with generic error."""
        mock_okx_client.get_positions.side_effect = OKXError("API error")

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/positions")

        assert response.status_code == 400

    def test_get_positions_unexpected_error(self, client, mock_okx_client):
        """Test positions route with unexpected error."""
        mock_okx_client.get_positions.side_effect = Exception("System error")

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/account/positions")

        assert response.status_code == 500
