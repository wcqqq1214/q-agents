"""Trading hours gatekeeper for US stock market."""

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

US_EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 31)
MARKET_CLOSE = time(16, 5)


def is_trading_hours() -> bool:
    """Return True when the current US Eastern time is within trading hours."""
    now_et = datetime.now(US_EASTERN)

    if now_et.weekday() >= 5:
        logger.debug(f"Weekend detected: {now_et.strftime('%A')}")
        return False

    current_time = now_et.time()
    if MARKET_OPEN <= current_time <= MARKET_CLOSE:
        logger.debug(f"Within trading hours: {current_time}")
        return True

    logger.debug(f"Outside trading hours: {current_time}")
    return False


def is_us_holiday() -> bool:
    """Return True when today is a US market holiday."""
    try:
        import pandas_market_calendars as mcal

        nyse = mcal.get_calendar("NYSE")
        now_et = datetime.now(US_EASTERN)
        today = now_et.date()
        schedule = nyse.valid_days(start_date=today, end_date=today)
        is_holiday = len(schedule) == 0
        if is_holiday:
            logger.info(f"US market holiday detected: {today}")
        return is_holiday
    except ImportError:
        logger.warning("pandas_market_calendars not installed, using basic weekend check")
        now_et = datetime.now(US_EASTERN)
        return now_et.weekday() >= 5


def should_update_stocks() -> bool:
    """Decide whether stock data should be updated now."""
    if is_us_holiday():
        logger.info("Skipping update: US market holiday")
        return False

    if not is_trading_hours():
        logger.info("Skipping update: outside trading hours")
        return False

    logger.info("✓ Gatekeeper passed: proceeding with stock update")
    return True
