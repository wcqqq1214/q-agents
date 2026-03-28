"""Tests for batch downloader."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.services.batch_downloader import download_daily_data, get_download_url


class TestGetDownloadUrl:
    """Tests for get_download_url function."""

    def test_get_url_for_1m_interval(self):
        """测试生成 1 分钟数据下载 URL"""
        url = get_download_url("BTCUSDT", "1m", date(2024, 1, 15))
        expected = "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-15.zip"
        assert url == expected

    def test_get_url_for_1d_interval(self):
        """测试生成 1 天数据下载 URL"""
        url = get_download_url("ETHUSDT", "1d", date(2024, 2, 20))
        expected = "https://data.binance.vision/data/spot/daily/klines/ETHUSDT/1d/ETHUSDT-1d-2024-02-20.zip"
        assert url == expected


class TestDownloadDailyData:
    """Tests for download_daily_data function."""

    @pytest.mark.asyncio
    async def test_download_success(self):
        """测试成功下载并解析数据"""
        mock_csv_content = b"1640995200000,46000.00,46500.00,45800.00,46200.00,100.5,1640998799999,4620000.00,1000,50.2,2310000.00,0\n"

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = mock_csv_content
            mock_response.raise_for_status = lambda: None
            mock_get.return_value = mock_response

            with patch("zipfile.ZipFile") as mock_zip:
                mock_zip_instance = MagicMock()
                mock_zip_instance.namelist.return_value = ["BTCUSDT-1m-2024-01-15.csv"]
                mock_zip_instance.read.return_value = mock_csv_content
                mock_zip.return_value.__enter__.return_value = mock_zip_instance

                result = await download_daily_data("BTCUSDT", "1m", date(2024, 1, 15))

                assert len(result) == 1
                assert result[0]["timestamp"] == 1640995200000
                assert result[0]["close"] == 46200.00

    @pytest.mark.asyncio
    async def test_download_handles_404(self):
        """测试处理 404 错误（数据不存在）"""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = Exception("404 Not Found")
            mock_get.return_value = mock_response

            result = await download_daily_data("BTCUSDT", "1m", date(2024, 1, 15))

            assert result == []

    @pytest.mark.asyncio
    async def test_download_parses_multiple_rows(self):
        """测试解析多行数据"""
        mock_csv_content = b"""1640995200000,46000.00,46500.00,45800.00,46200.00,100.5,1640998799999,4620000.00,1000,50.2,2310000.00,0
1640998800000,46200.00,46800.00,46100.00,46500.00,120.3,1641002399999,5580000.00,1100,60.1,2790000.00,0
"""

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = mock_csv_content
            mock_response.raise_for_status = lambda: None
            mock_get.return_value = mock_response

            with patch("zipfile.ZipFile") as mock_zip:
                mock_zip_instance = MagicMock()
                mock_zip_instance.namelist.return_value = ["BTCUSDT-1m-2024-01-15.csv"]
                mock_zip_instance.read.return_value = mock_csv_content
                mock_zip.return_value.__enter__.return_value = mock_zip_instance

                result = await download_daily_data("BTCUSDT", "1m", date(2024, 1, 15))

                assert len(result) == 2
                assert result[0]["timestamp"] == 1640995200000
                assert result[1]["timestamp"] == 1640998800000
