"""Tests for NYSE market calendar helpers."""

from datetime import date

from app.services.market_calendar import (
    count_nyse_trading_days,
    find_missing_trading_day_gaps,
    get_nyse_trading_days,
    is_nyse_trading_day,
)


def test_get_nyse_trading_days_skips_holiday_and_weekend():
    trading_days = get_nyse_trading_days(date(2025, 7, 1), date(2025, 7, 7))

    assert trading_days == (
        date(2025, 7, 1),
        date(2025, 7, 2),
        date(2025, 7, 3),
        date(2025, 7, 7),
    )
    assert count_nyse_trading_days(date(2025, 7, 1), date(2025, 7, 7)) == 4


def test_is_nyse_trading_day_distinguishes_holiday_from_trading_day():
    assert is_nyse_trading_day(date(2025, 7, 3)) is True
    assert is_nyse_trading_day(date(2025, 7, 4)) is False


def test_find_missing_trading_day_gaps_ignores_holidays():
    downloaded_dates = {
        date(2025, 7, 1),
        date(2025, 7, 2),
        date(2025, 7, 7),
    }

    gaps = find_missing_trading_day_gaps(
        downloaded_dates=downloaded_dates,
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 7),
    )

    assert gaps == [(date(2025, 7, 3), date(2025, 7, 3))]
