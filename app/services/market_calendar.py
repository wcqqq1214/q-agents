"""NYSE market calendar helpers."""

import logging
from datetime import date, timedelta
from functools import lru_cache

logger = logging.getLogger(__name__)

try:
    import pandas_market_calendars as mcal
except ImportError:  # pragma: no cover - dependency exists in normal runtime
    mcal = None


@lru_cache(maxsize=1)
def _get_nyse_calendar():
    """Return the NYSE calendar instance."""
    if mcal is None:
        raise ImportError("pandas_market_calendars is not installed")
    return mcal.get_calendar("NYSE")


def _weekday_range(start_date: date, end_date: date) -> tuple[date, ...]:
    """Fallback weekday range when the calendar package is unavailable."""
    if end_date < start_date:
        return ()

    trading_days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            trading_days.append(current)
        current += timedelta(days=1)
    return tuple(trading_days)


@lru_cache(maxsize=256)
def _cached_nyse_trading_days(start_date: date, end_date: date) -> tuple[date, ...]:
    """Cache NYSE trading-day lookups for repeated ranges."""
    if end_date < start_date:
        return ()

    try:
        schedule = _get_nyse_calendar().valid_days(start_date=start_date, end_date=end_date)
        return tuple(ts.date() for ts in schedule)
    except ImportError:
        logger.warning("pandas_market_calendars not installed, using basic weekday check")
        return _weekday_range(start_date, end_date)


def get_nyse_trading_days(start_date: date, end_date: date) -> tuple[date, ...]:
    """Return NYSE trading days between two dates, inclusive."""
    return _cached_nyse_trading_days(start_date, end_date)


def count_nyse_trading_days(start_date: date, end_date: date) -> int:
    """Return the number of NYSE trading days between two dates, inclusive."""
    return len(get_nyse_trading_days(start_date, end_date))


def is_nyse_trading_day(day: date) -> bool:
    """Return whether the provided date is an NYSE trading day."""
    return bool(get_nyse_trading_days(day, day))


def find_missing_trading_day_gaps(
    downloaded_dates: set[date], start_date: date, end_date: date
) -> list[tuple[date, date]]:
    """Return missing ranges using NYSE trading days instead of calendar days."""
    gaps: list[tuple[date, date]] = []
    gap_start: date | None = None
    previous_trading_day: date | None = None

    for trading_day in get_nyse_trading_days(start_date, end_date):
        if trading_day not in downloaded_dates:
            if gap_start is None:
                gap_start = trading_day
        elif gap_start is not None and previous_trading_day is not None:
            gaps.append((gap_start, previous_trading_day))
            gap_start = None

        previous_trading_day = trading_day

    if gap_start is not None and previous_trading_day is not None:
        gaps.append((gap_start, previous_trading_day))

    return gaps
