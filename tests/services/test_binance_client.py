"""Tests for Binance REST API client."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.binance_client import fetch_binance_klines, parse_kline_response


class TestParseKlineResponse:
    """Tests for parse_kline_response function."""

    def test_parse_single_kline(self):
        """测试解析单个 K 线数据"""
        raw_klines = [
            [
                1640995200000,  # Open time
                "46000.00",  # Open
                "46500.00",  # High
                "45800.00",  # Low
                "46200.00",  # Close
                "100.5",  # Volume
                1640998799999,  # Close time
                "4620000.00",  # Quote asset volume
                1000,  # Number of trades
                "50.2",  # Taker buy base asset volume
                "2310000.00",  # Taker buy quote asset volume
                "0",  # Ignore
            ]
        ]

        result = parse_kline_response(raw_klines)

        assert len(result) == 1
        assert result[0]["timestamp"] == 1640995200000
        assert result[0]["open"] == 46000.00
        assert result[0]["high"] == 46500.00
        assert result[0]["low"] == 45800.00
        assert result[0]["close"] == 46200.00
        assert result[0]["volume"] == 100.5
        assert "date" in result[0]

    def test_parse_multiple_klines(self):
        """测试解析多个 K 线数据"""
        raw_klines = [
            [
                1640995200000,
                "46000.00",
                "46500.00",
                "45800.00",
                "46200.00",
                "100.5",
                1640998799999,
                "4620000.00",
                1000,
                "50.2",
                "2310000.00",
                "0",
            ],
            [
                1640998800000,
                "46200.00",
                "46800.00",
                "46100.00",
                "46500.00",
                "120.3",
                1641002399999,
                "5580000.00",
                1100,
                "60.1",
                "2790000.00",
                "0",
            ],
        ]

        result = parse_kline_response(raw_klines)

        assert len(result) == 2
        assert result[0]["timestamp"] == 1640995200000
        assert result[1]["timestamp"] == 1640998800000

    def test_parse_empty_response(self):
        """测试解析空响应"""
        result = parse_kline_response([])
        assert result == []


class TestFetchBinanceKlines:
    """Tests for fetch_binance_klines function."""

    @pytest.mark.asyncio
    async def test_fetch_klines_success(self):
        """测试成功获取 K 线数据"""
        mock_response = [
            [
                1640995200000,
                "46000.00",
                "46500.00",
                "45800.00",
                "46200.00",
                "100.5",
                1640998799999,
                "4620000.00",
                1000,
                "50.2",
                "2310000.00",
                "0",
            ]
        ]

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(status_code=200, json=lambda: mock_response)
            mock_get.return_value.raise_for_status = lambda: None

            result = await fetch_binance_klines(
                symbol="BTCUSDT",
                interval="1m",
                start_time=1640995200000,
                end_time=1640998799999,
            )

            assert len(result) == 1
            assert result[0]["timestamp"] == 1640995200000
            assert result[0]["close"] == 46200.00

    @pytest.mark.asyncio
    async def test_fetch_klines_respects_limit(self):
        """测试 limit 参数限制"""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(status_code=200, json=lambda: [])
            mock_get.return_value.raise_for_status = lambda: None

            await fetch_binance_klines(
                symbol="BTCUSDT",
                interval="1m",
                start_time=1640995200000,
                end_time=1640998799999,
                limit=500,
            )

            # Verify the call was made with correct limit
            call_args = mock_get.call_args
            assert call_args[1]["params"]["limit"] == 500

    @pytest.mark.asyncio
    async def test_fetch_klines_max_limit_1000(self):
        """测试 limit 不超过 1000"""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(status_code=200, json=lambda: [])
            mock_get.return_value.raise_for_status = lambda: None

            await fetch_binance_klines(
                symbol="BTCUSDT",
                interval="1m",
                start_time=1640995200000,
                end_time=1640998799999,
                limit=2000,  # Request more than max
            )

            # Verify the call was made with max limit of 1000
            call_args = mock_get.call_args
            assert call_args[1]["params"]["limit"] == 1000
