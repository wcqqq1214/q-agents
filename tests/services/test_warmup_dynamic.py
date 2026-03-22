"""Tests for dynamic hot cache warmup functionality."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.realtime_agent import warmup_hot_cache, _convert_to_db_symbol


class TestConvertToDbSymbol:
    """Tests for symbol format conversion."""

    def test_convert_btcusdt(self):
        """Test converting BTCUSDT to BTC-USDT."""
        assert _convert_to_db_symbol("BTCUSDT") == "BTC-USDT"

    def test_convert_ethusdt(self):
        """Test converting ETHUSDT to ETH-USDT."""
        assert _convert_to_db_symbol("ETHUSDT") == "ETH-USDT"

    def test_convert_non_usdt_symbol(self):
        """Test converting non-USDT symbol returns as-is."""
        assert _convert_to_db_symbol("BTCETH") == "BTCETH"


class TestDynamicWarmup:
    """Tests for dynamic warmup logic."""

    @pytest.mark.asyncio
    async def test_warmup_empty_database(self):
        """Test warmup when database is empty - should fetch last 48 hours."""
        mock_klines = [
            {'timestamp': 1000, 'date': '2024-01-01T00:00:00+00:00',
             'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5, 'volume': 1000.0}
        ]

        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max:
            mock_get_max.return_value = None  # Empty database

            with patch('app.services.realtime_agent.fetch_binance_klines', new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = mock_klines

                with patch('app.services.realtime_agent.append_to_hot_cache') as mock_append:
                    await warmup_hot_cache()

                    # Should call fetch_binance_klines (not pagination) for 48h
                    assert mock_fetch.call_count == 4  # 2 symbols * 2 intervals

                    # Verify time range is approximately 48 hours
                    call_args = mock_fetch.call_args_list[0]
                    start_time = call_args[1]['start_time']
                    end_time = call_args[1]['end_time']
                    time_diff_hours = (end_time - start_time) / (1000 * 60 * 60)
                    assert 47 <= time_diff_hours <= 49

    @pytest.mark.asyncio
    async def test_warmup_small_gap(self):
        """Test warmup with gap <= 48 hours - should fill gap with pagination."""
        now = datetime.now(timezone.utc)
        # Database has data from 24 hours ago
        max_timestamp = int((now - timedelta(hours=24)).timestamp() * 1000)

        mock_klines = [
            {'timestamp': max_timestamp + 60000, 'date': '2024-01-01T00:01:00+00:00',
             'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5, 'volume': 1000.0}
        ]

        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max:
            mock_get_max.return_value = max_timestamp

            with patch('app.services.realtime_agent.fetch_klines_with_pagination', new_callable=AsyncMock) as mock_pagination:
                mock_pagination.return_value = mock_klines

                with patch('app.services.realtime_agent.append_to_hot_cache') as mock_append:
                    await warmup_hot_cache()

                    # Should use pagination for gap filling
                    assert mock_pagination.call_count == 4

                    # Verify start_time is max_timestamp + 1
                    call_args = mock_pagination.call_args_list[0]
                    start_time = call_args[1]['start_time']
                    assert start_time == max_timestamp + 1

    @pytest.mark.asyncio
    async def test_warmup_large_gap(self):
        """Test warmup with gap > 48 hours - should only fetch last 48 hours."""
        now = datetime.now(timezone.utc)
        # Database has data from 72 hours ago (large gap)
        max_timestamp = int((now - timedelta(hours=72)).timestamp() * 1000)

        mock_klines = [
            {'timestamp': 1000, 'date': '2024-01-01T00:00:00+00:00',
             'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5, 'volume': 1000.0}
        ]

        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max:
            mock_get_max.return_value = max_timestamp

            with patch('app.services.realtime_agent.fetch_binance_klines', new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = mock_klines

                with patch('app.services.realtime_agent.append_to_hot_cache') as mock_append:
                    await warmup_hot_cache()

                    # Should use regular fetch (not pagination) for last 48h only
                    assert mock_fetch.call_count == 4

                    # Verify time range is approximately 48 hours
                    call_args = mock_fetch.call_args_list[0]
                    start_time = call_args[1]['start_time']
                    end_time = call_args[1]['end_time']
                    time_diff_hours = (end_time - start_time) / (1000 * 60 * 60)
                    assert 47 <= time_diff_hours <= 49

    @pytest.mark.asyncio
    async def test_warmup_converts_symbol_format(self):
        """Test that warmup converts Binance symbol to database format."""
        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max:
            mock_get_max.return_value = None

            with patch('app.services.realtime_agent.fetch_binance_klines', new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = []

                with patch('app.services.realtime_agent.append_to_hot_cache'):
                    await warmup_hot_cache()

                    # Verify get_max_timestamp was called with converted symbols
                    calls = mock_get_max.call_args_list
                    symbols_queried = [call[0][0] for call in calls]
                    assert "BTC-USDT" in symbols_queried
                    assert "ETH-USDT" in symbols_queried

    @pytest.mark.asyncio
    async def test_warmup_handles_no_data_returned(self):
        """Test warmup handles case when API returns no data."""
        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max:
            mock_get_max.return_value = None

            with patch('app.services.realtime_agent.fetch_binance_klines', new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = []  # No data

                with patch('app.services.realtime_agent.append_to_hot_cache') as mock_append:
                    await warmup_hot_cache()

                    # Should not call append when no data
                    assert mock_append.call_count == 0

    @pytest.mark.asyncio
    async def test_warmup_handles_api_errors(self):
        """Test warmup continues on API errors."""
        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max:
            mock_get_max.return_value = None

            with patch('app.services.realtime_agent.fetch_binance_klines', new_callable=AsyncMock) as mock_fetch:
                mock_fetch.side_effect = Exception("API Error")

                # Should not raise exception
                await warmup_hot_cache()

    @pytest.mark.asyncio
    async def test_warmup_gap_exactly_48_hours(self):
        """Test warmup with gap exactly 48 hours - should use pagination."""
        now = datetime.now(timezone.utc)
        max_timestamp = int((now - timedelta(hours=48)).timestamp() * 1000)

        mock_klines = [{'timestamp': 1000, 'date': '2024-01-01T00:00:00+00:00',
                        'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5, 'volume': 1000.0}]

        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max:
            mock_get_max.return_value = max_timestamp

            with patch('app.services.realtime_agent.fetch_klines_with_pagination', new_callable=AsyncMock) as mock_pagination, \
                 patch('app.services.realtime_agent.fetch_binance_klines', new_callable=AsyncMock) as mock_fetch:
                mock_pagination.return_value = mock_klines
                mock_fetch.return_value = mock_klines

                with patch('app.services.realtime_agent.append_to_hot_cache'):
                    await warmup_hot_cache()

                    # Gap <= 48h, should use pagination (not regular fetch)
                    assert mock_pagination.call_count == 4
                    assert mock_fetch.call_count == 0

    @pytest.mark.asyncio
    async def test_warmup_gap_slightly_over_48_hours(self):
        """Test warmup with gap slightly over 48 hours - should fetch last 48h only."""
        now = datetime.now(timezone.utc)
        max_timestamp = int((now - timedelta(hours=48.5)).timestamp() * 1000)

        mock_klines = [{'timestamp': 1000, 'date': '2024-01-01T00:00:00+00:00',
                        'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5, 'volume': 1000.0}]

        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max:
            mock_get_max.return_value = max_timestamp

            with patch('app.services.realtime_agent.fetch_binance_klines', new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = mock_klines

                with patch('app.services.realtime_agent.append_to_hot_cache'):
                    await warmup_hot_cache()

                    # Gap > 48h, should use regular fetch
                    assert mock_fetch.call_count == 4

    @pytest.mark.asyncio
    async def test_warmup_integration(self):
        """Integration test with mocked database and API."""
        # Simulate database returning old timestamp (1 hour ago)
        now = datetime.now(timezone.utc)
        old_timestamp = int((now - timedelta(hours=1)).timestamp() * 1000)

        # Mock API to return new data
        new_data = [
            {'timestamp': old_timestamp + 60000, 'date': (now - timedelta(minutes=59)).isoformat(),
             'open': 105, 'high': 115, 'low': 95, 'close': 110, 'volume': 1100}
        ]

        with patch('app.services.realtime_agent.get_max_timestamp') as mock_get_max, \
             patch('app.services.realtime_agent.fetch_klines_with_pagination', new_callable=AsyncMock) as mock_fetch, \
             patch('app.services.realtime_agent.append_to_hot_cache'), \
             patch('app.services.realtime_agent.SYMBOLS', ['BTCUSDT']), \
             patch('app.services.realtime_agent.INTERVALS', ['1m']):

            mock_get_max.return_value = old_timestamp
            mock_fetch.return_value = new_data

            await warmup_hot_cache()

            # Verify API was called with correct start time
            assert mock_fetch.called
            call_args = mock_fetch.call_args_list[0]
            assert call_args[1]['start_time'] == old_timestamp + 1
