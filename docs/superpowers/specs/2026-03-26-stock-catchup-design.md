# Stock Data Startup Catch-up Mechanism

**Date**: 2026-03-26  
**Status**: Approved  
**Author**: Claude (Opus 4.6)

## Overview

Implement a startup catch-up mechanism for stock data to automatically fill gaps when the API server restarts after downtime. This prevents data gaps that occur when the server is offline during trading hours or across multiple days.

## Problem Statement

Currently, stock data updates only occur during US market trading hours (09:31-16:05 ET) via the `update_stocks_intraday` scheduler. If the API server is down or restarted outside trading hours, data gaps accumulate until the next trading session.

**Example scenario**:
- Last update: 2026-03-24 14:45 ET
- Server restarts: 2026-03-26 04:00 ET (before market open)
- Result: Missing data for 2026-03-25 and 2026-03-26

## Solution

Add a non-blocking background task that runs on API startup to detect and fill data gaps, with configurable lookback window and rate limiting to avoid Yahoo Finance API bans.

## Architecture

### Components

1. **Configuration Layer** (`app/config_manager.py`)
   - New method: `get_stock_catchup_config()`
   - Environment variables:
     - `STOCK_CATCHUP_DAYS=5` (default) - Maximum days to look back
     - `STOCK_RATE_LIMIT_DELAY=1.5` (default) - Delay between requests in seconds
     - `STOCK_CATCHUP_ENABLED=true` (default) - Enable/disable catch-up

2. **Catch-up Engine** (`app/services/stock_updater.py`)
   - Modified: `update_stocks_intraday(force: bool = False)` - Support bypass mode
   - New: `catchup_historical_stocks(days: int) -> dict` - Main catch-up logic
   - New: `_fetch_with_rate_limit(symbols, days, delay) -> dict` - Rate-limited fetcher

3. **Startup Integration** (`app/api/main.py`)
   - New: `background_stock_catchup()` - Background task wrapper
   - Modified: `lifespan()` - Launch catch-up task on startup

### Data Flow

```
API Startup
  ↓
Launch background_stock_catchup() (non-blocking)
  ↓
Check database metadata for last update date
  ↓
Calculate gap (today - last_update_date)
  ↓
Determine fetch window: min(gap, STOCK_CATCHUP_DAYS)
  ↓
Call update_stocks_intraday(force=True)
  ↓
Fetch data with rate limiting (1.5s delay per symbol)
  ↓
Save to database via upsert_ohlc_overwrite()
  ↓
Update metadata
  ↓
Log statistics and errors
```

## Detailed Implementation

### 3.1 Configuration Management

**File**: `app/config_manager.py`

Add new method:
```python
def get_stock_catchup_config() -> dict:
    """Get stock catch-up configuration from environment variables.
    
    Returns:
        dict with keys:
            - catchup_days: int - Maximum days to look back
            - rate_limit_delay: float - Delay between requests in seconds
            - enabled: bool - Whether catch-up is enabled
    """
    return {
        "catchup_days": int(os.getenv("STOCK_CATCHUP_DAYS", "5")),
        "rate_limit_delay": float(os.getenv("STOCK_RATE_LIMIT_DELAY", "1.5")),
        "enabled": os.getenv("STOCK_CATCHUP_ENABLED", "true").lower() == "true"
    }
```

**File**: `.env.example`

Add:
```bash
# Stock catch-up configuration
STOCK_CATCHUP_ENABLED=true
STOCK_CATCHUP_DAYS=5
STOCK_RATE_LIMIT_DELAY=1.5
```

### 3.2 Catch-up Engine

**File**: `app/services/stock_updater.py`

**Modify existing function**:
```python
async def update_stocks_intraday(force: bool = False) -> None:
    """Async wrapper for the intraday stock update.
    
    Args:
        force: If True, bypass trading hours check and update anyway
    """
    if not force and not should_update_stocks():
        logger.info("Skipping update: outside trading hours or holiday")
        return
        
    try:
        await asyncio.to_thread(update_stocks_intraday_sync)
    except Exception as exc:
        logger.error(f"Intraday update failed: {exc}", exc_info=True)
```

**Add new functions**:
```python
async def catchup_historical_stocks(days: int) -> dict:
    """Catch up missing historical stock data on startup.
    
    Args:
        days: Maximum number of days to look back
        
    Returns:
        Statistics dict with keys:
            - symbols_updated: int
            - records_added: int
            - date_range: tuple (start_date, end_date)
            - errors: list of error messages
    """
    logger.info(f"Starting stock catch-up (max {days} days)...")
    
    # Check last update date from metadata
    # Use AAPL as sentinel - assumes all symbols are updated together
    # Trade-off: Fast startup vs. handling symbols added at different times
    metadata = get_metadata("AAPL")
    
    if metadata is None:
        logger.info(f"No metadata found, fetching last {days} days")
        fetch_days = days
    else:
        last_date = datetime.fromisoformat(metadata["data_end"]).date()
        today = date.today()
        gap_days = (today - last_date).days
        
        if gap_days <= 1:
            logger.info(f"Stock data is up to date (last: {last_date})")
            return {
                "symbols_updated": 0,
                "records_added": 0,
                "date_range": None,
                "errors": []
            }
        
        fetch_days = min(gap_days, days)
        logger.info(f"Gap detected: {gap_days} days, fetching last {fetch_days} days")
    
    # Fetch with rate limiting
    config = get_stock_catchup_config()
    data_by_symbol = await _fetch_with_rate_limit(
        SYMBOLS, 
        fetch_days, 
        config["rate_limit_delay"]
    )
    
    # Save to database
    stats = {
        "symbols_updated": 0,
        "records_added": 0,
        "date_range": None,
        "errors": []
    }
    
    for symbol, records in data_by_symbol.items():
        try:
            if records:
                upsert_ohlc_overwrite(symbol, records)
                dates = [r["date"] for r in records]
                update_metadata(symbol, min(dates), max(dates))
                stats["symbols_updated"] += 1
                stats["records_added"] += len(records)
                
                if stats["date_range"] is None:
                    stats["date_range"] = (min(dates), max(dates))
                    
                logger.info(f"✓ {symbol}: {len(records)} records | Latest: {records[-1]['date']}")
        except Exception as exc:
            error_msg = f"{symbol}: {exc}"
            stats["errors"].append(error_msg)
            logger.error(f"Failed to save {symbol}: {exc}")
    
    logger.info(f"✓ Catch-up completed: {stats['symbols_updated']}/{len(SYMBOLS)} symbols updated")
    return stats


async def _fetch_with_rate_limit(
    symbols: List[str], 
    days: int, 
    delay: float
) -> Dict[str, List[Dict]]:
    """Fetch stock data with rate limiting to avoid Yahoo Finance ban.
    
    Args:
        symbols: List of stock symbols
        days: Number of days to fetch
        delay: Delay between requests in seconds
        
    Returns:
        Dict mapping symbol to list of OHLC records
    """
    result = {}
    
    for i, symbol in enumerate(symbols):
        try:
            # Add delay between requests (except first one)
            if i > 0:
                await asyncio.sleep(delay)
            
            # Fetch data for single symbol
            data = await asyncio.to_thread(
                fetch_recent_ohlc, 
                [symbol], 
                days
            )
            
            if symbol in data:
                result[symbol] = data[symbol]
                logger.debug(f"Fetched {len(data[symbol])} records for {symbol}")
            else:
                logger.warning(f"No data returned for {symbol}")
                
        except Exception as exc:
            logger.error(f"Failed to fetch {symbol}: {exc}")
            continue
    
    return result
```

### 3.3 Startup Integration

**File**: `app/api/main.py`

**Add new background task**:
```python
async def background_stock_catchup():
    """Background task for stock data catch-up on startup."""
    try:
        config = get_stock_catchup_config()
        if not config["enabled"]:
            logger.info("Stock catchup disabled by config")
            return
            
        logger.info(f"Starting stock catchup (max {config['catchup_days']} days)...")
        stats = await catchup_historical_stocks(days=config["catchup_days"])
        
        if stats["symbols_updated"] > 0:
            logger.info(
                f"✓ Stock catchup completed: {stats['symbols_updated']} symbols, "
                f"{stats['records_added']} records, range: {stats['date_range']}"
            )
        
        if stats["errors"]:
            logger.warning(f"Catchup errors: {stats['errors']}")
            
    except Exception as exc:
        logger.error(f"✗ Stock catchup failed: {exc}", exc_info=True)
```

**Modify lifespan function**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Finance Agent API...")
    app.state.arq_pool = await create_arq_pool()
    
    # ... existing initialization code ...
    
    # Start hot cache warmup as non-blocking background task
    warmup_task = asyncio.create_task(background_cache_warmup())
    logger.info("✓ Hot cache warmup started in background (non-blocking)")
    
    # Start hot cache update loop as background task
    update_task = asyncio.create_task(update_hot_cache_loop())
    logger.info("✓ Hot cache update loop started")
    
    # NEW: Start stock catchup as non-blocking background task
    catchup_task = asyncio.create_task(background_stock_catchup())
    logger.info("✓ Stock catchup started in background (non-blocking)")
    
    # ... existing scheduler setup ...
    
    yield
    
    # Shutdown
    logger.info("Shutting down Finance Agent API...")
    
    # Cancel warmup task if still running
    if not warmup_task.done():
        logger.info("Cancelling hot cache warmup task...")
        warmup_task.cancel()
        try:
            await warmup_task
        except asyncio.CancelledError:
            logger.info("✓ Hot cache warmup task cancelled")
    
    # Cancel update loop task
    update_task.cancel()
    try:
        await update_task
    except asyncio.CancelledError:
        pass
    
    # NEW: Cancel catchup task if still running
    if not catchup_task.done():
        logger.info("Cancelling stock catchup task...")
        catchup_task.cancel()
        try:
            await catchup_task
        except asyncio.CancelledError:
            logger.info("✓ Stock catchup task cancelled")
    
    scheduler.shutdown()
    await close_arq_pool(getattr(app.state, "arq_pool", None))
    logger.info("✓ Scheduler stopped")
```

## Error Handling

### 4.1 Error Handling Strategy

**Yahoo Finance Rate Limiting**:
- Catch `YFRateLimitError` per symbol
- Log warning and continue with other symbols
- Return errors in statistics dict
- Does NOT block API startup

**Network Timeouts**:
- yfinance default 10s timeout
- Single symbol failure does not affect others
- Logged as warnings

**Database Errors**:
- Transaction protection via SQLite
- Rollback on failure
- Existing data remains intact

### 4.2 Edge Cases

**Case 1: Database is empty**
- `get_metadata()` returns None
- Fallback: fetch last N days

**Case 2: Data is already up-to-date**
- Detect `data_end` is yesterday or today
- Skip catchup, log: "Stock data is up to date"

**Case 3: Gap exceeds configured days**
- Only fetch last `STOCK_CATCHUP_DAYS` days
- Log warning: "Gap exceeds catchup window"

**Case 4: Weekend/Holiday startup**
- Simply request last N days from yfinance
- yfinance automatically returns only valid trading days
- Database upsert handles duplicates gracefully
- **No need for pandas_market_calendars**

**Case 5: API restart during catchup**
- Task cancelled via `asyncio.CancelledError`
- Next startup will re-detect gap and retry

### 4.3 Logging Strategy

**Startup phase**:
```
INFO: Starting stock catchup (max 5 days)...
INFO: Gap detected: 3 days, fetching last 3 days
```

**Execution phase**:
```
INFO: ✓ AAPL: 3 records | Latest: 2026-03-25
WARNING: Failed to fetch GOOGL: YFRateLimitError
```

**Completion phase**:
```
INFO: ✓ Catchup completed: 6/7 symbols, 18 records, range: ('2026-03-23', '2026-03-25')
WARNING: Catchup errors: ['GOOGL: Rate limit']
```

## Testing Strategy

### 5.1 Unit Tests

**Test file**: `tests/test_stock_catchup.py`

Test cases:
1. `test_catchup_with_gap()` - Normal gap detection and fill
2. `test_catchup_no_gap()` - Skip when data is current
3. `test_catchup_empty_database()` - Handle missing metadata
4. `test_catchup_rate_limiting()` - Verify delays between requests
5. `test_catchup_partial_failure()` - Handle individual symbol failures
6. `test_force_bypass()` - Verify force=True bypasses trading hours check

### 5.2 Integration Tests

**Test scenarios**:
1. Start API with empty database → verify catchup runs
2. Start API with stale data → verify gap is filled
3. Start API with current data → verify catchup skips
4. Simulate Yahoo Finance rate limit → verify graceful degradation
5. Restart API during catchup → verify cancellation and retry

### 5.3 Manual Testing

**Verification steps**:
1. Set `STOCK_CATCHUP_DAYS=3` in `.env`
2. Delete recent data from database
3. Restart API server
4. Check logs for catchup execution
5. Verify database has filled data
6. Check API `/api/stocks/quotes` endpoint

## Implementation Checklist

- [ ] Add `get_stock_catchup_config()` to `app/config_manager.py`
- [ ] Add environment variables to `.env.example`
- [ ] Modify `update_stocks_intraday()` to support `force` parameter
- [ ] Add `catchup_historical_stocks()` function
- [ ] Add `_fetch_with_rate_limit()` function
- [ ] Add `background_stock_catchup()` to `app/api/main.py`
- [ ] Integrate catchup task into `lifespan()` function
- [ ] Add catchup task cancellation in shutdown
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Update documentation

## Benefits

1. **Automatic Gap Filling**: No manual intervention needed after downtime
2. **Non-blocking Startup**: API becomes available immediately
3. **Rate Limit Protection**: Avoids Yahoo Finance bans
4. **Configurable**: Adjust behavior via environment variables
5. **Robust Error Handling**: Single symbol failures don't break entire catchup
6. **Consistent with Crypto**: Follows same pattern as crypto hot cache warmup

## Trade-offs

1. **AAPL as Sentinel**: Uses AAPL metadata to determine if catchup is needed
   - Pro: Fast startup, simple logic
   - Con: Assumes all symbols updated together
   - Mitigation: Acceptable for current use case where symbols are batch-updated

2. **Fixed Delay Rate Limiting**: Uses simple sleep-based rate limiting
   - Pro: Simple, effective for small symbol count
   - Con: Not adaptive to actual API limits
   - Mitigation: 1.5s delay is conservative and works well

3. **No Trading Day Calculation**: Relies on yfinance to filter non-trading days
   - Pro: Simple, no extra dependencies
   - Con: May request data for weekends/holidays
   - Mitigation: yfinance handles this automatically, database upsert is idempotent

## Future Enhancements

1. **Adaptive Rate Limiting**: Adjust delay based on API response headers
2. **Per-Symbol Metadata**: Track each symbol independently
3. **Retry Logic**: Exponential backoff for failed symbols
4. **Metrics**: Expose catchup statistics via Prometheus/metrics endpoint
5. **Admin API**: Manual trigger endpoint for catchup

## Conclusion

This design provides a robust, non-blocking solution for filling stock data gaps on API startup. It follows established patterns from the crypto hot cache implementation, includes comprehensive error handling, and is configurable for different deployment scenarios.
