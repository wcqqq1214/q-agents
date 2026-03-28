"""Tests for daily crypto download with catch-up mechanism."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch


class TestDailyCryptoDownload:
    """Tests for daily_crypto_download function with catch-up logic."""

    @patch("app.api.main.download_daily_data", new_callable=AsyncMock)
    @patch("app.api.main.get_max_date")
    def test_downloads_yesterday_when_no_data_exists(self, mock_get_max_date, mock_download):
        """Test downloads yesterday's data when database is empty."""
        from app.api.main import daily_crypto_download

        mock_get_max_date.return_value = None
        mock_download.return_value = []

        daily_crypto_download()

        # Should download only yesterday
        yesterday = date.today() - timedelta(days=1)
        assert mock_download.call_count == 4  # 2 symbols * 2 intervals

    @patch("app.api.main.download_daily_data", new_callable=AsyncMock)
    @patch("app.api.main.get_max_date")
    def test_downloads_yesterday_when_data_is_current(self, mock_get_max_date, mock_download):
        """Test downloads only yesterday when data is already current."""
        from app.api.main import daily_crypto_download

        yesterday = date.today() - timedelta(days=1)
        mock_get_max_date.return_value = yesterday
        mock_download.return_value = []

        daily_crypto_download()

        # Should not download anything (data is current)
        assert mock_download.call_count == 0

    @patch("app.api.main.download_daily_data", new_callable=AsyncMock)
    @patch("app.api.main.get_max_date")
    def test_catches_up_on_missing_dates(self, mock_get_max_date, mock_download):
        """Test downloads all missing dates when there's a gap."""
        from app.api.main import daily_crypto_download

        # Simulate 3 days of missing data
        max_date = date.today() - timedelta(days=4)
        mock_get_max_date.return_value = max_date
        mock_download.return_value = []

        daily_crypto_download()

        # Should download 3 missing days for each symbol/interval
        # (yesterday, 2 days ago, 3 days ago)
        assert mock_download.call_count == 12  # 3 days * 2 symbols * 2 intervals

    @patch("app.api.main.download_daily_data", new_callable=AsyncMock)
    @patch("app.api.main.get_max_date")
    def test_continues_on_download_failure(self, mock_get_max_date, mock_download):
        """Test continues downloading other dates when one fails."""
        from app.api.main import daily_crypto_download

        max_date = date.today() - timedelta(days=3)
        mock_get_max_date.return_value = max_date

        # Make first call fail, rest succeed
        mock_download.side_effect = [
            Exception("Network error"),  # First call fails
            [],  # Rest succeed
            [],
            [],
            [],
            [],
            [],
            [],
        ]

        # Should not raise exception
        daily_crypto_download()

        # Should have attempted all downloads despite failure
        assert mock_download.call_count == 8  # 2 days * 2 symbols * 2 intervals

    @patch("app.api.main.download_daily_data", new_callable=AsyncMock)
    @patch("app.api.main.get_max_date")
    @patch("app.api.main.logger")
    def test_logs_statistics(self, mock_logger, mock_get_max_date, mock_download):
        """Test logs download statistics."""
        from app.api.main import daily_crypto_download

        max_date = date.today() - timedelta(days=3)
        mock_get_max_date.return_value = max_date

        # Simulate some failures
        mock_download.side_effect = [
            Exception("Error 1"),
            [{"data": 1}],
            [{"data": 2}],
            Exception("Error 2"),
            [{"data": 3}],
            [{"data": 4}],
            [{"data": 5}],
            [{"data": 6}],
        ]

        daily_crypto_download()

        # Verify statistics were logged
        info_calls = [call for call in mock_logger.info.call_args_list]

        # Should log completion with statistics
        completion_log = str(info_calls[-1])
        assert "completed" in completion_log.lower()
        assert "total" in completion_log.lower() or "8" in completion_log

    @patch("app.api.main.download_daily_data", new_callable=AsyncMock)
    @patch("app.api.main.get_max_date")
    def test_handles_different_max_dates_per_symbol_interval(
        self, mock_get_max_date, mock_download
    ):
        """Test handles different max dates for different symbol/interval combinations."""
        from app.api.main import daily_crypto_download

        # Return different max dates for different symbol/interval combinations
        def get_max_date_side_effect(symbol, interval):
            if symbol == "BTCUSDT" and interval == "1m":
                return date.today() - timedelta(days=3)
            elif symbol == "BTCUSDT" and interval == "1d":
                return date.today() - timedelta(days=2)
            elif symbol == "ETHUSDT" and interval == "1m":
                return date.today() - timedelta(days=1)
            else:  # ETHUSDT 1d
                return date.today() - timedelta(days=1)

        mock_get_max_date.side_effect = get_max_date_side_effect
        mock_download.return_value = []

        daily_crypto_download()

        # BTCUSDT 1m: 2 missing days
        # BTCUSDT 1d: 1 missing day
        # ETHUSDT 1m: 0 missing days (already current)
        # ETHUSDT 1d: 0 missing days (already current)
        # Total: 3 downloads
        assert mock_download.call_count == 3

    @patch("app.api.main.download_daily_data", new_callable=AsyncMock)
    @patch("app.api.main.get_max_date")
    def test_no_download_when_today_is_max_date(self, mock_get_max_date, mock_download):
        """Test no download when max date is today (edge case)."""
        from app.api.main import daily_crypto_download

        mock_get_max_date.return_value = date.today()
        mock_download.return_value = []

        daily_crypto_download()

        # Should not download anything (no missing dates)
        assert mock_download.call_count == 0
