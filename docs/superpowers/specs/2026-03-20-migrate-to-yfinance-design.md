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
- `get_us_stock_quote` - Already exists, used for real-time quotes
- `get_stock_data` or similar - Need to verify if historical OHLC interface exists
- If missing: Either extend MCP server or create direct yfinance client

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
| No data for range | Date range has no trading days | Return empty array, log info |
| Rate limiting | Too many requests | Exponential backoff, retry |
| Network timeout | Connection issues | Retry with backoff (max 3) |
| Parse error | Unexpected data format | Log error, return 500 |

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

### Phase 1: MCP Server Investigation (Priority: Critical)

**Objective**: Determine if MCP yfinance server supports historical data retrieval.

**Tasks**:
1. Write test script to list all available MCP tools
2. Check for historical data endpoints (e.g., `get_stock_data`, `get_history`)
3. Test endpoint parameters and response format
4. Document findings

**Decision Point**:
- **If MCP has historical data**: Proceed with MCP integration
- **If MCP lacks historical data**:
  - Option A: Extend MCP server with new tool (recommended)
  - Option B: Create direct yfinance client wrapper

**Estimated Time**: 30 minutes

### Phase 2: Frontend Quick Fix (Priority: High, Independent)

**Objective**: Fix K-line chart English localization.

**Tasks**:
1. Modify `KLineChart.tsx` to add localization config
2. Test in browser with different locale settings
3. Verify English dates display correctly

**Files**:
- `frontend/src/components/chart/KLineChart.tsx`

**Estimated Time**: 15 minutes

### Phase 3: Backend Data Source Migration (Priority: High)

**Objective**: Switch all OHLC and quote data from Polygon to yfinance/MCP.

**Tasks**:
1. Extend `app/mcp_client/finance_client.py` with history function
2. Update `app/scripts/init_ohlc_data.py` to use MCP client
3. Update `app/tasks/update_ohlc.py` to use MCP client
4. Add comprehensive error handling
5. Test data retrieval for all 7 stocks

**Files**:
- `app/mcp_client/finance_client.py`
- `app/scripts/init_ohlc_data.py`
- `app/tasks/update_ohlc.py`

**Estimated Time**: 1-2 hours

### Phase 4: Remove Logo Functionality (Priority: Medium)

**Objective**: Clean up logo-related code.

**Tasks**:
1. Remove logo field from `StockQuote` model (or make optional)
2. Remove logo fetching in `stocks.py`
3. Update frontend components to not display logo
4. Update TypeScript types

**Files**:
- `app/api/models/schemas.py`
- `app/api/routes/stocks.py`
- `frontend/src/lib/types.ts`
- `frontend/src/components/stock/StockSelector.tsx` (if applicable)

**Estimated Time**: 30 minutes

### Phase 5: Database Re-initialization (Priority: High)

**Objective**: Populate database with 5 years of historical data.

**Tasks**:
1. Backup existing database (optional)
2. Clear OHLC and metadata tables
3. Run initialization script
4. Verify data range: 2021-03-20 to 2026-03-20
5. Verify data quality (no gaps, correct values)

**Commands**:
```bash
# Backup (optional)
cp app/data/finance.db app/data/finance.db.backup

# Clear and reinitialize
uv run python -c "from app.database import get_conn; conn = get_conn(); conn.execute('DELETE FROM ohlc'); conn.execute('DELETE FROM metadata'); conn.commit(); conn.close()"

# Run init script
uv run python -m app.scripts.init_ohlc_data
```

**Estimated Time**: 30 minutes (including API calls)

### Phase 6: Testing & Validation (Priority: Critical)

**Objective**: Ensure all functionality works correctly.

**Test Cases**:

**Backend**:
- [ ] MCP client can fetch 5 years of OHLC data
- [ ] Stock quotes API returns correct data without logo
- [ ] OHLC API returns correct data from database
- [ ] Polygon news API still works
- [ ] Error handling works for invalid tickers
- [ ] Error handling works for network failures

**Frontend**:
- [ ] K-line chart displays English dates
- [ ] K-line chart loads and displays correctly
- [ ] Stock cards display without logo
- [ ] Chart zoom and pan work correctly
- [ ] Error messages display properly

**Integration**:
- [ ] Full flow: Select stock → Load chart → Display data
- [ ] Multiple stocks can be loaded sequentially
- [ ] Page refresh maintains functionality

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

- [ ] K-line chart displays English dates only
- [ ] Database contains 5 years of OHLC data (2021-2026)
- [ ] Stock quotes display correctly without logos
- [ ] All 7 stocks load successfully
- [ ] No Polygon API calls for OHLC or quotes
- [ ] Polygon news functionality unchanged
- [ ] No regressions in existing features

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
| MCP server lacks historical data API | High | Medium | Extend MCP server or use direct yfinance |
| yfinance rate limiting | Medium | Low | Add delays, implement backoff |
| Data format incompatibility | High | Low | Validate and transform data |
| 5-year data unavailable | High | Low | Verify with test before full migration |
| Frontend breaking changes | Medium | Low | Test thoroughly, keep changes minimal |

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

