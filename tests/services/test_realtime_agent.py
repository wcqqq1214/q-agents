"""Tests for realtime agent."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.realtime_agent import update_hot_cache, warmup_hot_cache


class TestWarmupHotCache:
    """Tests for warmup_hot_cache function."""

    @pytest.mark.asyncio
    async def test_warmup_fetches_48_hours_of_data(self):
        """测试预热获取 48 小时数据"""
        mock_klines = [
            {
                "timestamp": 1000,
                "date": "2024-01-01T00:00:00+00:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000.0,
            }
        ]

        with patch(
            "app.services.realtime_agent.fetch_binance_klines", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = mock_klines

            with patch("app.services.realtime_agent.append_to_hot_cache") as mock_append:
                await warmup_hot_cache()

                # Should call fetch for both symbols and both intervals
                assert mock_fetch.call_count == 4  # 2 symbols * 2 intervals
                assert mock_append.call_count == 4

    @pytest.mark.asyncio
    async def test_warmup_calculates_correct_time_range(self):
        """测试预热计算正确的时间范围"""
        with patch(
            "app.services.realtime_agent.fetch_binance_klines", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = []

            with patch("app.services.realtime_agent.append_to_hot_cache"):
                await warmup_hot_cache()

                # Check first call arguments
                call_args = mock_fetch.call_args_list[0]
                start_time = call_args[1]["start_time"]
                end_time = call_args[1]["end_time"]

                # Should be approximately 48 hours
                time_diff_ms = end_time - start_time
                time_diff_hours = time_diff_ms / (1000 * 60 * 60)
                assert 47 <= time_diff_hours <= 49  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_warmup_handles_api_errors(self):
        """测试预热处理 API 错误"""
        with patch(
            "app.services.realtime_agent.fetch_binance_klines", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.side_effect = Exception("API Error")

            # Should not raise exception
            await warmup_hot_cache()


class TestUpdateHotCache:
    """Tests for update_hot_cache function."""

    @pytest.mark.asyncio
    async def test_update_fetches_recent_data(self):
        """测试更新获取最近数据"""
        mock_klines = [
            {
                "timestamp": 2000,
                "date": "2024-01-01T00:01:00+00:00",
                "open": 101.0,
                "high": 102.0,
                "low": 100.0,
                "close": 101.5,
                "volume": 1100.0,
            }
        ]

        with patch(
            "app.services.realtime_agent.fetch_binance_klines", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = mock_klines

            with patch("app.services.realtime_agent.append_to_hot_cache") as mock_append:
                with patch("app.services.realtime_agent.cleanup_hot_cache") as mock_cleanup:
                    await update_hot_cache()

                    # Should call fetch for both symbols and both intervals
                    assert mock_fetch.call_count == 4
                    assert mock_append.call_count == 4
                    assert mock_cleanup.call_count == 4

    @pytest.mark.asyncio
    async def test_update_cleans_old_data(self):
        """测试更新清理旧数据"""
        with patch(
            "app.services.realtime_agent.fetch_binance_klines", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = []

            with patch("app.services.realtime_agent.append_to_hot_cache"):
                with patch("app.services.realtime_agent.cleanup_hot_cache") as mock_cleanup:
                    await update_hot_cache()

                    # Verify cleanup was called with correct cutoff time
                    assert mock_cleanup.call_count == 4
                    call_args = mock_cleanup.call_args_list[0]
                    cutoff_time = call_args[0][2]
                    assert isinstance(cutoff_time, datetime)
