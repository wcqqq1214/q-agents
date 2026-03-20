# Migration to yfinance Data Source - Design Document

**Date:** 2026-03-20
**Status:** Draft
**Author:** System

## Overview

This document outlines the design for migrating the Finance Agent application from Polygon.io to yfinance as the primary data source for stock quotes and OHLC (Open, High, Low, Close) historical data. Polygon.io will be retained exclusively for historical news retrieval.

## Background

### Current Issues

1. **K-line Chart Localization**: The chart's x-axis displays Chinese text due to browser locale detection
2. **Limited Historical Data**: Polygon.io free tier only provides 2 years of historical data (2024-03-18 to 2026-03-18), but we need 5 years (2021-03-20 to 2026-03-20)

### Current Architecture

- **Stock Quotes**: MCP yfinance server → Backend API → Frontend
- **OHLC Data**: Polygon.io → Database → Backend API → Frontend
- **News**: Polygon.io → Backend API → Frontend
- **Company Info/Logo**: Polygon.io → Backend API → Frontend

## Goals

1. Migrate OHLC historical data retrieval from Polygon to yfinance (via MCP Server)
2. Migrate stock quote retrieval to use yfinance consistently (already using MCP)
3. Fix K-line chart to display English dates only
4. Remove logo display functionality (simplification)
5. Retain Polygon.io exclusively for historical news
6. Obtain 5 years of historical OHLC data

## Design Decisions

### Data Source Strategy

| Data Type | Current Source | New Source | Rationale |
|-----------|---------------|------------|-----------|
| Stock Quotes | MCP/yfinance | MCP/yfinance | No change needed |
| OHLC Historical | Polygon.io | MCP/yfinance | Free, 5+ years data |
| Company Logo | Polygon.io | None | Simplification |
| News | Polygon.io | Polygon.io | Keep existing |

### MCP Server Integration

**Approach**: Use MCP yfinance server as the unified interface for all yfinance data access.

**Why MCP Server?**
- Centralized yfinance access
- Consistent error handling
- Rate limiting management
- Easier to mock/test

**Required MCP Tools**:
- `get_us_stock_quote` - ✅ Already exists, used for real-time quotes
- `get_stock_history` - ❌ **DOES NOT EXIST** - Must be added to MCP server

**Critical Finding**: The existing `get_stock_data` tool returns technical indicators (SMA, MACD, Bollinger Bands) but NOT raw OHLC data. We must extend the MCP server with a new tool.

**New MCP Tool Specification**:
```python
@mcp.tool()
def get_stock_history(ticker: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Fetch historical OHLC data for a ticker.

    Args:
        ticker: Stock symbol (e.g., AAPL)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Dict with:
        - ticker: str
        - data: List[{date, open, high, low, close, volume}]

    Implementation:
        yf.Ticker(ticker).history(start=start_date, end=end_date)
    """
```

## Architecture Changes

### Backend Components

#### 1. MCP Client Extension (`app/mcp_client/finance_client.py`)

**New Functions**:
```python
async def _call_get_stock_history_async(
    ticker: str,
    start_date: str,
    end_date: str,
    url: str
) -> List[Dict[str, Any]]:
    """Call MCP server to get historical OHLC data."""
    # Returns list of {date, open, high, low, close, volume}

def call_get_stock_history(
    ticker: str,
    start_date: str,
    end_date: str
) -> List[Dict[str, Any]]:
    """Synchronous wrapper for stock history."""
```

**Modified Functions**:
- Keep existing `call_get_us_stock_quote()` unchanged

#### 2. OHLC Initialization Script (`app/scripts/init_ohlc_data.py`)

**Changes**:
```python
# Before
from app.polygon.client import fetch_ohlc

# After
from app.mcp_client.finance_client import call_get_stock_history

# Update fetch logic
data = call_get_stock_history(symbol, start_date, end_date)
```

**Error Handling**:
- Retry on network failures (max 3 retries)
- Log detailed errors for each symbol
- Continue processing other symbols on individual failures
- Add rate limiting delays between requests (if needed)

#### 3. Stock Quotes API (`app/api/routes/stocks.py`)

**Changes**:
```python
# Remove
from app.polygon.client import fetch_ticker_details

# In _fetch_single_quote()
# Remove logo fetching
logo = await asyncio.to_thread(fetch_ticker_details, symbol)

# Update StockQuote creation
quote = StockQuote(
    symbol=symbol,
    name=name,
    price=data.get("price"),
    change=data.get("change"),
    change_percent=data.get("change_percent"),
    # logo=logo,  # Remove this line
    timestamp=datetime.now(timezone.utc).isoformat(),
)
```

#### 4. OHLC Update Task (`app/tasks/update_ohlc.py`)

**Changes**:
- Replace Polygon client import with MCP client
- Update error handling for yfinance-specific errors
- Maintain same scheduling logic

#### 5. Data Models (`app/api/models/schemas.py`)

**Changes**:
```python
class StockQuote(BaseModel):
    symbol: str
    name: str
    price: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None
    # logo: Optional[str] = None  # Remove or make optional
    timestamp: Optional[str] = None
    error: Optional[str] = None
```

### Frontend Components

#### 1. K-Line Chart (`frontend/src/components/chart/KLineChart.tsx`)

**Changes**:
```typescript
// In createChart() call
const chart = createChart(chartContainerRef.current, {
  width: chartContainerRef.current.clientWidth,
  height: 400,
  localization: {
    locale: 'en-US',
    dateFormat: 'yyyy-MM-dd',
  },
  layout: {
    background: { color: 'transparent' },
    textColor: '#d1d5db',
  },
  // ... rest of config
});
```

**Why This Works**:
- `locale: 'en-US'` forces English month/day names
- `dateFormat` ensures consistent date display format
- Overrides browser's default locale detection

#### 2. Stock Card/Display Components

**Changes**:
- Remove logo display elements
- Update TypeScript types to make logo optional
- Show stock symbol initials or placeholder icon instead

**Files to Check**:
- `frontend/src/components/stock/StockSelector.tsx`
- Any component that displays `StockQuote` data

### Database

**No Schema Changes Required**:
- OHLC table structure remains the same
- Metadata table structure remains the same
- Only data source changes, not data format

**Data Migration**:
```sql
-- Clear existing data
DELETE FROM ohlc;
DELETE FROM metadata;

-- Run init script to populate with 5 years of data
-- uv run python -m app.scripts.init_ohlc_data
```

## Error Handling Strategy

### yfinance-Specific Errors

| Error Type | Cause | Handling |
|------------|-------|----------|
| Invalid ticker | Symbol doesn't exist | Return 404, log warning |
| No data for range | Date range has no trading days | Return empty array with 200, log info |
| Invalid date range | end_date < start_date | Return 400, log warning |
| Future dates | start_date > today | Adjust to today, log info |
| Empty result set | No trading days in range (weekends/holidays) | Return empty array with 200, log info |
| Rate limiting | Too many requests | Exponential backoff, retry |
| Network timeout | Connection issues | Retry with backoff (max 3) |
| Parse error | Unexpected data format | Log error, return 500 |
| yfinance data quality | Missing/incorrect data | Log warning, return partial data |

### Error Propagation

```
yfinance → MCP Server → MCP Client → API Route → Frontend
         ↓            ↓             ↓           ↓
      Log error   Transform    Add context  Show toast
```

**Principles**:
- Fail gracefully at each layer
- Log detailed errors server-side
- Return user-friendly messages to frontend
- Don't expose internal error details to users

## Implementation Plan

### Phase 1: Extend MCP Server (Priority: Critical, Blocking)

**Objective**: Add historical OHLC data endpoint to MCP yfinance server.

**Tasks**:
1. Locate MCP server code: `mcp_servers/market_data/main.py`
2. Add new tool `get_stock_history(ticker, start_date, end_date)`
3. Implement using `yf.Ticker(ticker).history(start=start_date, end=end_date)`
4. Return format: `{ticker: str, data: [{date, open, high, low, close, volume}]}`
5. Test with sample request for AAPL 2021-2026
6. Restart MCP server

**Files**:
- `mcp_servers/market_data/main.py`

**Estimated Time**: 30-45 minutes

### Phase 2: Frontend Quick Fix (Priority: High, Independent)

**Objective**: Fix K-line chart English localization.

**Tasks**:
1. Modify `KLineChart.tsx` - **ADD** new `localization` property to createChart config (line ~95)
2. Insert before `layout` property:
   ```typescript
   localization: {
     locale: 'en-US',
     dateFormat: 'yyyy-MM-dd',
   },
   ```
3. Test in browser with zh-CN locale setting
4. Verify English dates display correctly in chart and tooltips

**Files**:
- `frontend/src/components/chart/KLineChart.tsx` (line 95-113)

**Estimated Time**: 15 minutes

### Phase 3: Backend Data Source Migration (Priority: High)

**Objective**: Switch all OHLC and quote data from Polygon to yfinance/MCP.

**Tasks**:
1. Extend `app/mcp_client/finance_client.py` with history function
2. Update `app/scripts/init_ohlc_data.py` to use MCP client
3. Add rate limiting: `time.sleep(0.5)` between symbol fetches (respectful to Yahoo Finance)
4. Update `app/tasks/update_ohlc.py` to use MCP client
5. Add comprehensive error handling for date ranges, network failures
6. Test data retrieval for all 7 stocks

**Files**:
- `app/mcp_client/finance_client.py`
- `app/scripts/init_ohlc_data.py`
- `app/tasks/update_ohlc.py`

**Estimated Time**: 1-2 hours

### Phase 4: Remove Logo Functionality (Priority: Medium)

**Objective**: Clean up logo-related code.

**Tasks**:
1. Remove logo field from `StockQuote` model (or make optional)
2. Remove logo fetching in `stocks.py` (lines 31, 45)
3. Update frontend: No changes needed - StockCard.tsx already handles missing logos gracefully (lines 40-55)
4. Update TypeScript types in `frontend/src/lib/types.ts`
5. Audit all imports of `app.polygon.client` - keep only `fetch_news` for news functionality
6. Add comment to `polygon/client.py`: "Only fetch_news is used; OHLC migrated to yfinance"
7. Update `.env.example` to clarify `POLYGON_API_KEY` is optional (news only)

**Files**:
- `app/api/models/schemas.py`
- `app/api/routes/stocks.py`
- `frontend/src/lib/types.ts`
- `frontend/src/components/stock/StockSelector.tsx` (if applicable)

**Estimated Time**: 30 minutes

### Phase 5: Database Re-initialization (Priority: High)

**Objective**: Populate database with 5 years of historical data.

**Tasks**:
1. **Stop backend server** (if running) to prevent concurrent access
2. Backup existing database:
   ```bash
   cp app/data/finance.db app/data/finance.db.polygon-backup-$(date +%Y%m%d)
   ```
3. Clear OHLC and metadata tables:
   ```bash
   uv run python -c "from app.database import get_conn; conn = get_conn(); conn.execute('DELETE FROM ohlc'); conn.execute('DELETE FROM metadata'); conn.commit(); conn.close()"
   ```
4. Run initialization script:
   ```bash
   uv run python -m app.scripts.init_ohlc_data
   ```
5. Verify data range and quality:
   ```bash
   uv run python -c "from app.database import get_conn; conn = get_conn(); result = conn.execute('SELECT symbol, COUNT(*) as cnt, MIN(date) as earliest, MAX(date) as latest FROM ohlc GROUP BY symbol').fetchall(); print('\\n'.join([f\"{r['symbol']}: {r['cnt']} records, {r['earliest']} to {r['latest']}\" for r in result])); conn.close()"
   ```
6. Expected results:
   - Each symbol: ~1,260 records (5 years of trading days)
   - Date range: ~2021-03-20 to 2026-03-20
   - No major gaps (allow holidays/weekends)
7. **Restart backend server**

**Estimated Time**: 30 minutes (including API calls)

### Phase 6: Testing & Validation (Priority: Critical)

**Objective**: Ensure all functionality works correctly.

**Test Cases**:

**Backend**:
- [ ] MCP server has `get_stock_history` tool available
- [ ] MCP client can fetch 5 years of OHLC data for AAPL
- [ ] Database validation:
  ```bash
  # Record count per symbol (expected: ~1,260)
  SELECT symbol, COUNT(*) FROM ohlc GROUP BY symbol;

  # Date range per symbol (expected: 2021-03-20 to 2026-03-20)
  SELECT symbol, MIN(date), MAX(date) FROM ohlc GROUP BY symbol;

  # Check for weekday gaps (should be minimal, holidays OK)
  ```
- [ ] Stock quotes API returns correct data without logo field
- [ ] OHLC API returns correct data from database
- [ ] Polygon news API still works (fetch_news function)
- [ ] Error handling: Invalid ticker returns 404
- [ ] Error handling: Network failure retries with backoff

**Frontend**:
- [ ] K-line chart displays English dates (test with browser locale set to zh-CN)
- [ ] Chart tooltip shows "yyyy-MM-dd" format, not localized
- [ ] K-line chart loads and displays correctly for all 7 stocks
- [ ] Stock cards display without logo (shows fallback)
- [ ] Chart zoom and pan work correctly
- [ ] Error messages display properly for invalid symbols

**Integration**:
- [ ] Full flow: Select stock → Load chart → Display data
- [ ] Multiple stocks can be loaded sequentially
- [ ] Page refresh maintains functionality
- [ ] No console errors related to missing logo

**Performance**:
- [ ] Initialization completes in < 5 minutes for all 7 stocks
- [ ] OHLC API responds in < 500ms for 5-year range
- [ ] Database size < 50MB after initialization

**Estimated Time**: 1 hour

## Rollback Plan

If migration fails or causes issues:

1. **Immediate Rollback** (< 5 minutes):
   ```bash
   git checkout HEAD -- app/api/routes/stocks.py app/scripts/init_ohlc_data.py
   cp app/data/finance.db.backup app/data/finance.db
   ```

2. **Partial Rollback**:
   - Keep frontend localization fix (independent)
   - Revert backend data source changes
   - Restore Polygon integration

3. **Data Recovery**:
   - Restore database from backup
   - Re-run Polygon initialization script

## Success Criteria

- [ ] K-line chart displays English dates only (verified in zh-CN locale)
- [ ] Database contains 5 years of OHLC data (2021-2026)
- [ ] Each symbol has ~1,260 trading day records
- [ ] Stock quotes display correctly without logos
- [ ] All 7 stocks load successfully
- [ ] No Polygon API calls for OHLC or quotes
- [ ] Polygon news functionality unchanged
- [ ] No regressions in existing features
- [ ] Initialization completes in < 5 minutes
- [ ] OHLC API responds in < 500ms for 5-year range
- [ ] Database size < 50MB after initialization

## Dependencies

**External**:
- MCP yfinance server must be running
- Internet connection for yfinance data
- Polygon API key (for news only)

**Internal**:
- Python dependencies: mcp, yfinance (via MCP)
- Database: SQLite with existing schema
- Frontend: lightweight-charts library

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| MCP server lacks historical data API | High | Confirmed | Extend MCP server with get_stock_history tool (Phase 1) |
| yfinance rate limiting | Medium | Low | Add 0.5s delays between requests; implement backoff |
| yfinance data quality issues | High | Medium | Implement data validation checks; log anomalies; verify against known values |
| yfinance library breaking changes | Medium | Low | Pin yfinance version in MCP server; monitor GitHub releases |
| Data format incompatibility | High | Low | Validate and transform data; comprehensive testing |
| 5-year data unavailable | High | Low | Verified in testing - yfinance provides 5+ years |
| Frontend breaking changes | Medium | Low | Test thoroughly, keep changes minimal |
| Concurrent access during migration | Medium | Medium | Stop backend server before database operations |
| Database corruption during migration | High | Low | Backup before clearing; verify after initialization |

## Future Considerations

1. **Logo Restoration**: If logos are needed later, consider:
   - Third-party logo APIs (Clearbit, Financial Modeling Prep)
   - Static logo assets
   - Generated avatars from ticker symbols

2. **Data Source Diversification**: Consider fallback data sources if yfinance becomes unreliable

3. **Caching Strategy**: Implement Redis caching for frequently accessed historical data

4. **Real-time Updates**: Consider WebSocket integration for live price updates

## References

- yfinance documentation: https://pypi.org/project/yfinance/
- lightweight-charts localization: https://tradingview.github.io/lightweight-charts/docs/api/interfaces/LocalizationOptions
- MCP protocol: https://modelcontextprotocol.io/

