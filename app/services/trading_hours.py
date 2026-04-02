"""Trading hours gatekeeper for US stock market."""

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.services.market_calendar import is_nyse_trading_day

logger = logging.getLogger(__name__)

US_EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 31)
MARKET_CLOSE = time(16, 5)


def is_trading_hours() -> bool:
    """Return True when the current US Eastern time is within trading hours."""
    now_et = datetime.now(US_EASTERN)

    if not is_nyse_trading_day(now_et.date()):
        logger.debug(f"Market closed day detected: {now_et.date()}")
        return False

    current_time = now_et.time()
    if MARKET_OPEN <= current_time <= MARKET_CLOSE:
        logger.debug(f"Within trading hours: {current_time}")
        return True

    logger.debug(f"Outside trading hours: {current_time}")
    return False


def is_us_holiday() -> bool:
    """Return True when today is a US market holiday."""
    now_et = datetime.now(US_EASTERN)
    today = now_et.date()
    is_holiday = not is_nyse_trading_day(today)
    if is_holiday:
        logger.info(f"US market holiday detected: {today}")
    return is_holiday


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
