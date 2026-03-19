# Stock Selector and Chat Interface Design

**Date:** 2026-03-19
**Status:** Approved
**Approach:** Real-time Data-Driven (Option A)

## Overview

Redesign the Home page to include a real-time stock selector for the Magnificent Seven stocks and transform the Query panel into a ChatGPT-style single-turn Q&A interface. The left panel displays compact stock cards with live pricing and a reserved area for K-line charts. The right panel provides a chat interface where users can ask questions about selected stocks and receive structured analysis results.

## Requirements

### Functional Requirements

1. **Stock Selector (Left Panel - Top)**
   - Display 7 US tech stocks (Magnificent Seven) in compact cards
   - Show: company logo, stock symbol, current price, change percentage with color coding
   - Support stock selection (single selection at a time)
   - Auto-refresh pricing data every 60 seconds
   - Manual refresh button
   - 2-column grid layout for compact display

2. **K-Line Chart Area (Left Panel - Bottom)**
   - Reserved space for future implementation
   - Placeholder or empty state for now

3. **Chat Interface (Right Panel)**
   - Single-turn Q&A mode (no conversation history)
   - Input box at bottom with dynamic placeholder based on selected stock
   - Submit button (disabled when no stock selected or analyzing)
   - Expandable result card showing structured analysis
   - Real-time progress updates via SSE
   - Clear previous results on new submission

4. **Analysis Results**
   - Structured display with collapsible sections:
     - Technical Analysis
     - News Summary
     - Social Sentiment
     - Recommendation
   - Progress indicators during analysis
   - Error handling with user-friendly messages

### Non-Functional Requirements

1. **Performance**
   - Stock quotes cached for 5-10 seconds on backend
   - Pause auto-refresh when page not visible
   - Lazy loading for heavy components

2. **Reliability**
   - Graceful degradation when APIs fail
   - Fallback for logo loading failures
   - SSE connection error handling

3. **Usability**
   - Responsive layout
   - Clear visual feedback for all interactions
   - Accessible color coding (not relying solely on color)

## Architecture

### Component Hierarchy

```
HomePage
├── StockSelector (left-top)
│   ├── StockCard × 7
│   └── RefreshButton
├── ChartArea (left-bottom - reserved)
└── ChatPanel (right)
    ├── MessageArea
    │   ├── UserMessage (optional)
    │   └── ResultCard (expandable)
    │       ├── ProgressSection
    │       └── StructuredResult
    │           ├── TechnicalAnalysis
    │           ├── NewsSummary
    │           ├── SocialSentiment
    │           └── Recommendation
    └── InputBox (fixed bottom)
```

### Page Layout

```
┌─────────────────────────────────────────────────────────┐
│                      Navbar                              │
└─────────────────────────────────────────────────────────┘
┌──────────────────────┬──────────────────────────────────┐
│  Left Panel (65%)    │   Right Panel (35%)              │
│                      │                                  │
│ ┌──────────────────┐ │ ┌──────────────────────────────┐ │
│ │ Stock Selector   │ │ │   Chat Interface             │ │
│ │ (Compact Cards)  │ │ │                              │ │
│ │ - 7 stocks       │ │ │   [Messages Area]            │ │
│ │ - 2 columns      │ │ │                              │ │
│ │ Height: 40%      │ │ │                              │ │
│ └──────────────────┘ │ │                              │ │
│                      │ │                              │ │
│ ┌──────────────────┐ │ │   [Input Box - Bottom]       │ │
│ │ K-Line Chart     │ │ └──────────────────────────────┘ │
│ │ (Reserved)       │ │                                  │
│ │ Height: 60%      │ │                                  │
│ └──────────────────┘ │                                  │
└──────────────────────┴──────────────────────────────────┘
```

## Data Models

### Type Definitions Location

All new TypeScript interfaces should be added to the existing `/home/wcqqq21/finance-agent/frontend/src/lib/types.ts` file to maintain consistency with the current codebase.

### Frontend Types

```typescript
interface StockInfo {
  symbol: string;          // Stock symbol, e.g., "AAPL"
  name: string;            // Company name, e.g., "Apple Inc."
  logo: string;            // Logo URL
  price: number;           // Current price
  change: number;          // Price change
  changePercent: number;   // Change percentage
  lastUpdate: string;      // Last update timestamp
}

interface ChatState {
  selectedStock: string | null;     // Currently selected stock symbol
  userQuery: string;                 // User input query
  isAnalyzing: boolean;              // Analysis in progress flag
  progress: string[];                // Progress messages
  result: AnalysisResult | null;     // Analysis result
}

interface AnalysisResult {
  query: string;                     // Original query
  symbol: string;                    // Analyzed stock
  timestamp: string;                 // Analysis timestamp
  technical?: TechnicalAnalysis;     // Technical analysis section
  news?: NewsSummary;                // News summary section
  social?: SocialSentiment;          // Social sentiment section
  recommendation?: string;           // Final recommendation
}

interface TechnicalAnalysis {
  price: number;
  indicators: Record<string, any>;
  trend: string;
  signals: string[];
}

interface NewsSummary {
  articles: NewsArticle[];
  sentiment: string;
  sentimentScore: number;
}

interface NewsArticle {
  title: string;
  url: string;
  source: string;
  published_time: string;
  snippet?: string;
}

interface SocialSentiment {
  platform: string;
  sentiment: string;
  sentimentScore: number;
  topics: string[];
}
```

### Magnificent Seven Stocks

```typescript
const MAGNIFICENT_SEVEN = [
  { symbol: 'AAPL', name: 'Apple Inc.' },
  { symbol: 'MSFT', name: 'Microsoft Corporation' },
  { symbol: 'GOOGL', name: 'Alphabet Inc.' },
  { symbol: 'AMZN', name: 'Amazon.com Inc.' },
  { symbol: 'NVDA', name: 'NVIDIA Corporation' },
  { symbol: 'META', name: 'Meta Platforms Inc.' },
  { symbol: 'TSLA', name: 'Tesla Inc.' },
];
```

## API Design

### New Endpoint: Batch Stock Quotes

```
GET /api/stocks/quotes?symbols=AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA

Response:
{
  "quotes": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "price": 178.50,
      "change": 2.30,
      "changePercent": 1.31,
      "logo": "https://...",
      "timestamp": "2026-03-19T10:30:00Z"
    },
    {
      "symbol": "INVALID",
      "error": "Symbol not found"
    }
  ]
}
```

**Implementation:**
- Use existing MCP market data tools with `asyncio.gather()` to fetch quotes in parallel
- Fetch logos from Polygon.io API (`/v3/reference/tickers/{ticker}` returns `branding.logo_url`)
  - Add new `fetch_ticker_details()` function to `app/polygon/client.py`
  - Cache logos for 24 hours (they rarely change)
- Cache quote responses for 10 seconds to reduce API calls
- Return 200 with partial data if some symbols fail (include `error` field for failed symbols)
- Handle Polygon.io rate limits (5 req/min) by prioritizing Clearbit Logo API for logos

### Existing Endpoint: Analysis (Adjusted)

```
POST /api/analyze
Body: { "query": "分析 AAPL 的技术指标和最新新闻" }

Or via SSE:
GET /api/analyze/stream?query=分析+AAPL
```

**Adjustments:**
- Align with existing `Report` schema in `app/api/models/schemas.py`:
  - Use existing field names: `quant_analysis`, `news_sentiment`, `social_sentiment`
  - Frontend `AnalysisResult` maps to backend `Report`:
    - `technical` ← `quant_analysis`
    - `news` ← `news_sentiment`
    - `social` ← `social_sentiment`
    - `recommendation` ← `final_decision` (from CIO agent output)
- Update CIO system prompt to output structured JSON instead of plain text
- SSE event types (standardized):
  - `progress`: Progress updates during analysis
  - `result`: Final structured result
  - `error`: Error messages
  - Remove `status` type for consistency

### Data Flow

```
Frontend                Backend                 MCP Servers
   │                       │                         │
   │──GET /stocks/quotes──>│                         │
   │                       │──get_us_stock_quote────>│
   │                       │<────────────────────────│
   │<──────────────────────│                         │
   │                       │                         │
   │──POST /analyze───────>│                         │
   │<──SSE progress────────│                         │
   │<──SSE progress────────│──Multi-agent graph─────>│
   │<──SSE result──────────│<────────────────────────│
```

## Component Design

### StockSelector Component

**Responsibilities:**
- Fetch and display real-time stock quotes
- Handle stock selection
- Auto-refresh every 60 seconds
- Manual refresh on demand

**Props:**
```typescript
interface StockSelectorProps {
  onStockSelect: (symbol: string) => void;
  selectedStock: string | null;
}
```

**State:**
```typescript
const [stocks, setStocks] = useState<StockInfo[]>([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);
```

**Behavior:**
- On mount: fetch initial quotes
- Set interval: refresh every 60 seconds
- Pause refresh when `document.visibilityState === 'hidden'`
- Clear interval on unmount

**Example visibility check:**
```typescript
useEffect(() => {
  const handleVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
      // Resume refresh
    } else {
      // Pause refresh
    }
  };
  document.addEventListener('visibilitychange', handleVisibilityChange);
  return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
}, []);
```

### StockCard Component

**Responsibilities:**
- Display individual stock information
- Visual feedback for selection and hover states
- Color-coded change percentage

**Props:**
```typescript
interface StockCardProps {
  stock: StockInfo;
  selected: boolean;
  onClick: () => void;
}
```

**Visual Design:**
- Compact card with padding: 12px
- Layout: Flex row with logo (32x32), info column, change badge
- Selected state: border-2 border-primary
- Hover state: shadow-md transition
- Change color: green (positive), red (negative), gray (zero)
- Change icon: ↑ (positive), ↓ (negative)

### ChatPanel Component

**Responsibilities:**
- Manage chat state (query, analysis, results)
- Handle SSE connection for real-time updates
- Display structured analysis results
- Clear results on new submission

**Props:**
```typescript
interface ChatPanelProps {
  selectedStock: string | null;
}
```

**State:**
```typescript
const [query, setQuery] = useState('');
const [isAnalyzing, setIsAnalyzing] = useState(false);
const [progress, setProgress] = useState<string[]>([]);
const [result, setResult] = useState<AnalysisResult | null>(null);
```

**Behavior:**
- Input placeholder changes based on `selectedStock`:
  - No stock selected: `"Select a stock to start analysis"`
  - Stock selected: `"Ask about {symbol}... (e.g., technical analysis, recent news)"`
- Submit disabled when `!selectedStock || isAnalyzing`
- On submit: clear previous results, start SSE connection
- SSE events:
  - `progress`: append to progress array
  - `result`: set result and close connection
  - `error`: show toast and close connection
- On unmount: close active SSE connection

### ResultCard Component

**Responsibilities:**
- Display structured analysis results
- Collapsible sections for each analysis type
- Progress indicators during analysis

**Props:**
```typescript
interface ResultCardProps {
  query: string;
  symbol: string;
  progress: string[];
  result: AnalysisResult | null;
  isAnalyzing: boolean;
}
```

**Sections:**
1. **Header**: Query + Symbol + Timestamp
2. **Progress** (if analyzing): List of progress messages
3. **Technical Analysis** (collapsible): Indicators, trend, signals
4. **News Summary** (collapsible): Articles, sentiment score
5. **Social Sentiment** (collapsible): Platform, sentiment, topics
6. **Recommendation** (always expanded): Final decision

## Error Handling

### Stock Quotes Fetch Failure

**Scenario:** Backend API fails or MCP server unavailable

**Handling:**
- Display last successful data with "Data may be outdated" badge
- If never fetched successfully, show placeholder ("--")
- Toast notification: "Failed to refresh stock data"
- Retry button available

### Analysis Request Failure

**Scenario:** SSE connection drops or backend error

**Handling:**
- SSE disconnect: Display "Connection interrupted, please retry"
- Backend error: Show error message in result card
- Timeout (30s): Auto-cancel and prompt user to retry
- Toast notification with error details

### Logo Loading Failure

**Scenario:** Logo URL returns 404 or fails to load

**Handling:**
- Fallback to generic stock icon
- Or display first letter of symbol in colored circle
- No error notification (silent fallback)

## Edge Cases

### No Stock Selected on Submit

**Prevention:** Input and button disabled when `selectedStock === null`

**Fallback:** If user bypasses frontend, backend returns 400 error

### Switch Stock During Analysis

**Behavior:**
- Allow stock switching
- Current analysis continues unaffected
- Input placeholder updates to new stock
- User can submit new query after current analysis completes

### Submit During Analysis

**Prevention:** Submit button disabled when `isAnalyzing === true`

**Alternative:** Cancel current analysis and start new one (optional enhancement)

### Network Slow/Offline

**Handling:**
- Show loading skeleton for stock cards
- Timeout after 10 seconds with friendly error message
- Retry mechanism available

### Market Hours and Stale Data

**Scenario:** Market is closed (after-hours, weekends, holidays)

**Handling:**
- Display last available price with timestamp
- Add badge: "Market Closed" or "After Hours"
- Show when market opens next (optional enhancement)
- Price changes still show last session's change

**Currency Display:**
- Format prices with currency symbol: `$178.50`
- Use locale-aware formatting: `new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })`


## Performance Optimization

### Stock Quote Refresh

**Strategy:**
- Use `useSWR` or `react-query` for caching and auto-refresh
- Pause refresh when page not visible (`document.visibilityState`)
- Debounce manual refresh button (prevent spam)

### Result Rendering

**Strategy:**
- Virtual scrolling for large result sets
- Lazy load chart components (K-line area)
- Memoize expensive computations

### SSE Connection Management

**Strategy:**
- Close EventSource on component unmount
- Prevent memory leaks with proper cleanup
- Reuse connection for multiple progress events

## Configuration Constants

```typescript
// Frontend
const STOCK_REFRESH_INTERVAL = 60000;  // 60 seconds
const NETWORK_TIMEOUT = 10000;          // 10 seconds
const ANALYSIS_TIMEOUT = 30000;         // 30 seconds

// Backend
const QUOTE_CACHE_TTL = 10;             // 10 seconds
const LOGO_CACHE_TTL = 86400;           // 24 hours
const POLYGON_RATE_LIMIT = 5;           // 5 requests per minute
```

## Logo Acquisition Strategy

**Priority Order:**

1. **Polygon.io API** (Primary)
   - Endpoint: `GET /v3/reference/tickers/{ticker}`
   - Field: `results.branding.logo_url`
   - Requires: Existing `POLYGON_API_KEY`

2. **Clearbit Logo API** (Fallback)
   - URL: `https://logo.clearbit.com/{domain}`
   - Example: `https://logo.clearbit.com/apple.com`
   - No API key required

3. **Local Static Images** (Last Resort)
   - Store logos in `frontend/public/logos/`
   - Filename: `{symbol}.png`
   - Manually curated for 7 stocks

## Implementation Phases

### Phase 1: Backend API (Priority)

1. Create `/api/stocks/quotes` endpoint
2. Implement parallel batch quote fetching using `asyncio.gather()`
3. Create `fetch_ticker_details()` function in `app/polygon/client.py` for logo fetching
4. Add response caching (10 seconds TTL for quotes, 24 hours for logos)
5. Adjust `/api/analyze` SSE to use standardized event types (`progress`, `result`, `error`)
6. Update CIO agent system prompt to output structured JSON

### Phase 2: Frontend Components

1. Create `StockSelector` and `StockCard` components
2. Implement auto-refresh logic
3. Create new `ChatPanel` component (replace `QueryPanel`)
4. Create `ResultCard` with collapsible sections
5. Update `HomePage` layout

### Phase 3: Integration & Testing

1. Connect frontend to new backend APIs
2. Test SSE streaming with structured results
3. Verify error handling scenarios
4. Performance testing and optimization

### Phase 4: Polish & Enhancement

1. Add loading skeletons
2. Improve animations and transitions
3. Accessibility audit
4. Mobile responsiveness:
   - Breakpoint < 768px: Stack layout (stock selector on top, chat below)
   - Stock cards: Single column on mobile
   - Hide K-line chart on mobile (show only on desktop)
   - Full-width chat panel on mobile

## Testing Strategy

### Unit Tests

- `StockCard`: rendering, selection, color coding
- `ChatPanel`: state management, SSE handling
- `ResultCard`: section rendering, collapsing

### Integration Tests

- Stock selection → input placeholder update
- Submit query → SSE progress → result display
- Auto-refresh → data update → UI refresh

### E2E Tests

- Full user flow: select stock → ask question → view results
- Error scenarios: network failure, API errors
- Performance: auto-refresh, multiple submissions

## Accessibility

- Color-coded changes include icons (↑↓) for colorblind users
- All interactive elements keyboard accessible
- ARIA labels for stock cards and buttons
- Screen reader announcements for analysis progress
- Focus management in chat interface

## Future Enhancements

1. **K-Line Chart Integration**
   - Use TradingView widget or Chart.js
   - Display historical price data
   - Interactive zoom and pan

2. **Multi-Stock Comparison**
   - Select multiple stocks
   - Side-by-side analysis
   - Comparative charts

3. **Conversation History**
   - Save previous Q&A sessions
   - Quick access to past analyses
   - Export/share functionality

4. **Advanced Filters**
   - Custom stock lists beyond Magnificent Seven
   - Sector-based grouping
   - Watchlist management

5. **Real-Time Alerts**
   - Price alerts
   - News alerts
   - Sentiment change notifications

## Dependencies

### New Frontend Dependencies

- None (use existing UI components and hooks)

### New Backend Dependencies

- None (use existing MCP tools and LangGraph agents)

### External APIs

- Polygon.io (already configured)
- Clearbit Logo API (optional, no key required)

## Risks & Mitigations

### Risk: Polygon.io Rate Limits

**Mitigation:**
- Implement aggressive caching (5-10s)
- Batch requests where possible
- Fallback to Clearbit for logos

### Risk: SSE Connection Instability

**Mitigation:**
- Implement reconnection logic
- Timeout and error handling
- Fallback to polling if SSE fails repeatedly

### Risk: CIO Agent Output Format Change

**Mitigation:**
- Add output schema validation
- Graceful degradation if structure missing
- Backward compatibility layer

### Risk: Performance Degradation with Auto-Refresh

**Mitigation:**
- Pause refresh when page hidden
- Debounce refresh requests
- Monitor and adjust refresh interval

## Success Metrics

- Stock quote refresh latency < 2s
- Analysis request completion < 30s
- Zero SSE connection failures in normal conditions
- 100% logo load success rate (with fallbacks)
- User can complete full flow in < 10 clicks

## Conclusion

This design provides a modern, real-time stock analysis interface with clear separation between stock selection and query interaction. The real-time data approach ensures users always see current market information, while the structured result display makes analysis insights easy to digest. The design is scalable for future enhancements like K-line charts and conversation history.
