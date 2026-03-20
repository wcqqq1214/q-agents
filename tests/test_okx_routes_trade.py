"""Tests for OKX trading management routes."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.okx.exceptions import (
    OKXAuthError,
    OKXRateLimitError,
    OKXConfigError,
    OKXError,
    OKXInsufficientBalanceError,
    OKXOrderError
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
    mock.place_order = AsyncMock()
    mock.cancel_order = AsyncMock()
    mock.get_order_details = AsyncMock()
    mock.get_order_history = AsyncMock()
    return mock


class TestPlaceOrderRoute:
    """Tests for POST /api/okx/trade/order endpoint."""

    def test_place_limit_order(self, client, mock_okx_client):
        """Test placing a limit order."""
        mock_okx_client.place_order.return_value = {
            'order_id': '12345',
            'client_order_id': 'my_order_1',
            'status_code': '0'
        }

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.post("/api/okx/trade/order", json={
                'mode': 'demo',
                'inst_id': 'BTC-USDT',
                'side': 'buy',
                'order_type': 'limit',
                'size': '0.01',
                'price': '50000',
                'client_order_id': 'my_order_1'
            })

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'demo'
        assert data['order_id'] == '12345'
        assert data['client_order_id'] == 'my_order_1'
        assert data['status_code'] == '0'

    def test_place_market_order(self, client, mock_okx_client):
        """Test placing a market order."""
        mock_okx_client.place_order.return_value = {
            'order_id': '67890',
            'client_order_id': None,
            'status_code': '0'
        }

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.post("/api/okx/trade/order", json={
                'mode': 'live',
                'inst_id': 'ETH-USDT',
                'side': 'sell',
                'order_type': 'market',
                'size': '1.5'
            })

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'live'
        assert data['order_id'] == '67890'
        assert data['status_code'] == '0'

    def test_place_order_with_client_order_id(self, client, mock_okx_client):
        """Test placing order with client order ID."""
        mock_okx_client.place_order.return_value = {
            'order_id': '11111',
            'client_order_id': 'custom_id_123',
            'status_code': '0'
        }

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.post("/api/okx/trade/order", json={
                'mode': 'demo',
                'inst_id': 'BTC-USDT',
                'side': 'buy',
                'order_type': 'limit',
                'size': '0.1',
                'price': '45000',
                'client_order_id': 'custom_id_123'
            })

        assert response.status_code == 200
        data = response.json()
        assert data['client_order_id'] == 'custom_id_123'

    def test_place_order_insufficient_balance(self, client, mock_okx_client):
        """Test placing order with insufficient balance."""
        mock_okx_client.place_order.side_effect = OKXInsufficientBalanceError(
            "Insufficient balance", code="51008"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.post("/api/okx/trade/order", json={
                'mode': 'demo',
                'inst_id': 'BTC-USDT',
                'side': 'buy',
                'order_type': 'market',
                'size': '100'
            })

        assert response.status_code == 400
        data = response.json()
        assert 'Insufficient balance' in data['detail']

    def test_place_order_error(self, client, mock_okx_client):
        """Test placing order with order error."""
        mock_okx_client.place_order.side_effect = OKXOrderError(
            "Order size too small", code="51020"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.post("/api/okx/trade/order", json={
                'mode': 'demo',
                'inst_id': 'BTC-USDT',
                'side': 'buy',
                'order_type': 'limit',
                'size': '0.00001',
                'price': '50000'
            })

        assert response.status_code == 400
        data = response.json()
        assert 'Order size too small' in data['detail']

    def test_place_order_auth_error(self, client, mock_okx_client):
        """Test placing order with authentication error."""
        mock_okx_client.place_order.side_effect = OKXAuthError(
            "Invalid API key", code="50113"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.post("/api/okx/trade/order", json={
                'mode': 'live',
                'inst_id': 'BTC-USDT',
                'side': 'buy',
                'order_type': 'market',
                'size': '0.01'
            })

        assert response.status_code == 401

    def test_place_order_rate_limit(self, client, mock_okx_client):
        """Test placing order with rate limit error."""
        mock_okx_client.place_order.side_effect = OKXRateLimitError(
            "Rate limit exceeded", code="50011"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.post("/api/okx/trade/order", json={
                'mode': 'demo',
                'inst_id': 'BTC-USDT',
                'side': 'buy',
                'order_type': 'market',
                'size': '0.01'
            })

        assert response.status_code == 429


class TestCancelOrderRoute:
    """Tests for DELETE /api/okx/trade/order/{order_id} endpoint."""

    def test_cancel_order_by_order_id(self, client, mock_okx_client):
        """Test canceling order by order ID."""
        mock_okx_client.cancel_order.return_value = {
            'order_id': '12345',
            'client_order_id': None,
            'status_code': '0'
        }

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.delete("/api/okx/trade/order/12345?mode=demo&inst_id=BTC-USDT")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'demo'
        assert data['order_id'] == '12345'
        assert data['status_code'] == '0'

    def test_cancel_order_not_found(self, client, mock_okx_client):
        """Test canceling non-existent order."""
        mock_okx_client.cancel_order.side_effect = OKXOrderError(
            "Order not found", code="51400"
        )

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.delete("/api/okx/trade/order/99999?mode=demo&inst_id=BTC-USDT")

        assert response.status_code == 400
        data = response.json()
        assert 'Order not found' in data['detail']


class TestGetOrderDetailsRoute:
    """Tests for GET /api/okx/trade/order/{order_id} endpoint."""

    def test_get_order_details(self, client, mock_okx_client):
        """Test getting order details."""
        mock_okx_client.get_order_details.return_value = {
            'order_id': '12345',
            'inst_id': 'BTC-USDT',
            'side': 'buy',
            'order_type': 'limit',
            'size': '0.01',
            'price': '50000',
            'status': 'filled'
        }

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/trade/order/12345?mode=demo&inst_id=BTC-USDT")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'demo'
        assert data['order']['order_id'] == '12345'
        assert data['order']['status'] == 'filled'


class TestGetOrderHistoryRoute:
    """Tests for GET /api/okx/trade/orders/history endpoint."""

    def test_get_order_history(self, client, mock_okx_client):
        """Test getting order history."""
        mock_okx_client.get_order_history.return_value = [
            {
                'order_id': '12345',
                'inst_id': 'BTC-USDT',
                'side': 'buy',
                'status': 'filled'
            },
            {
                'order_id': '67890',
                'inst_id': 'ETH-USDT',
                'side': 'sell',
                'status': 'canceled'
            }
        ]

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/trade/orders/history?mode=demo")

        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'demo'
        assert len(data['orders']) == 2
        assert data['orders'][0]['order_id'] == '12345'

    def test_get_order_history_empty(self, client, mock_okx_client):
        """Test getting empty order history."""
        mock_okx_client.get_order_history.return_value = []

        with patch('app.api.routes.okx.get_okx_client', return_value=mock_okx_client):
            response = client.get("/api/okx/trade/orders/history?mode=demo")

        assert response.status_code == 200
        data = response.json()
        assert data['orders'] == []
