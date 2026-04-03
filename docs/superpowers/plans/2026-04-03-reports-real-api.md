# Reports Real API Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mock-backed `/reports` page with real backend report data, add backend-owned `asset_type` to the reports contract, preserve the accordion UX and manual refresh button, and delete the unused report detail placeholder page.

**Architecture:** Backend owns report classification and API normalization, so both newly generated and historical reports expose a stable `Report` contract. Frontend consumes that normalized contract directly and keeps the existing accordion UI, adding only fetch/refresh/loading behavior plus cleanup of mock-only code.

**Tech Stack:** FastAPI, Pydantic, pytest, Next.js 16, React 19, TypeScript strict mode, shadcn/ui, pnpm, uv

---

## File Structure

- Create: `app/reporting/asset_type.py`
  Responsibility: shared backend helper for `stocks`/`crypto` classification used by report writing and API fallback reads.
- Modify: `app/graph_multi.py`
  Responsibility: write `asset_type` into aggregated `report.json`.
- Modify: `app/api/models/schemas.py`
  Responsibility: make the API `Report` schema expose `asset_type` and normalized defaults for `query`/`reports`.
- Modify: `app/api/routes/reports.py`
  Responsibility: normalize historical `report.json` payloads and return stable report responses for both list/detail endpoints.
- Create: `tests/test_reports_routes.py`
  Responsibility: route-level contract coverage for stored and inferred `asset_type`, plus normalization of legacy `query`/`reports`.
- Create: `tests/test_reporting_asset_type.py`
  Responsibility: focused unit coverage for backend `stocks`/`crypto` classification rules.
- Modify: `tests/test_multi_agent_graph.py`
  Responsibility: verify newly written aggregated reports include `asset_type`.
- Modify: `frontend/src/lib/types.ts`
  Responsibility: align frontend `Report` type with the real backend contract.
- Modify: `frontend/src/components/reports/ReportCard.tsx`
  Responsibility: consume the real `Report` type and keep rendering safely from normalized fields.
- Create: `frontend/src/components/reports/ReportsListSkeleton.tsx`
  Responsibility: encapsulate loading placeholders for the reports list using existing `Skeleton`.
- Modify: `frontend/src/app/reports/page.tsx`
  Responsibility: load reports from the API on entry, support manual refresh, render loading/empty states, and stop using mock data.
- Delete: `frontend/src/app/reports/[id]/page.tsx`
  Responsibility: remove the unused placeholder route.
- Delete: `frontend/src/lib/mock-data/reports.ts`
  Responsibility: remove dead mock-only data once no imports remain.

## Chunk 1: Backend Contract And Compatibility

### Task 1: Shared asset-type helper and aggregated report writer

**Files:**
- Create: `app/reporting/asset_type.py`
- Create: `tests/test_reporting_asset_type.py`
- Modify: `app/graph_multi.py`
- Modify: `tests/test_multi_agent_graph.py`

- [ ] **Step 1: Write the failing tests**

```python
from app.reporting.asset_type import classify_asset_type


def test_classify_asset_type_handles_crypto_and_stocks() -> None:
    assert classify_asset_type(" BTC ") == "crypto"
    assert classify_asset_type("btc-usd") == "crypto"
    assert classify_asset_type("NVDA") == "stocks"


# Extend the existing CIO aggregation test with:
report_obj = json.loads(report_path.read_text(encoding="utf-8"))
assert report_obj["symbol"] == "NVDA"
assert report_obj["asset_type"] == "stocks"
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_reporting_asset_type.py tests/test_multi_agent_graph.py -q`

Expected:
- FAIL because `app.reporting.asset_type` does not exist yet
- and/or FAIL because `report.json` does not contain `asset_type`

- [ ] **Step 3: Write the minimal implementation**

```python
# app/reporting/asset_type.py
from typing import Literal
import re

AssetType = Literal["stocks", "crypto"]

CRYPTO_TICKERS = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK"}


def classify_asset_type(asset: str) -> AssetType:
    normalized = (asset or "").strip().upper()
    if re.search(r"\b[A-Z]{2,10}-USD\b", normalized):
        return "crypto"
    if normalized in CRYPTO_TICKERS:
        return "crypto"
    return "stocks"
```

```python
# app/graph_multi.py
from app.reporting.asset_type import classify_asset_type

# inside _build_aggregated_report return payload
"symbol": asset,
"asset_type": classify_asset_type(asset),
```

- [ ] **Step 4: Run the tests again and confirm they pass**

Run: `uv run pytest tests/test_reporting_asset_type.py tests/test_multi_agent_graph.py -q`

Expected:
- PASS
- the new asset-type assertions are green

- [ ] **Step 5: Commit**

```bash
git add app/reporting/asset_type.py app/graph_multi.py tests/test_reporting_asset_type.py tests/test_multi_agent_graph.py
git commit -m "feat(reporting): persist asset type in aggregated reports"
```

### Task 2: Reports API normalization for new and historical report files

**Files:**
- Modify: `app/api/models/schemas.py`
- Modify: `app/api/routes/reports.py`
- Create: `tests/test_reports_routes.py`

- [ ] **Step 1: Write the failing route tests**

```python
def test_get_reports_returns_stored_asset_type(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import app

    report_dir = tmp_path / "data" / "reports" / "20260403_120000_NVDA"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text(json.dumps({
        "symbol": "NVDA",
        "timestamp": "2026-04-03T04:00:00Z",
        "asset_type": "stocks",
        "query": "Analyze NVDA",
        "reports": {"cio": "x", "quant": None, "news": None, "social": None},
    }), encoding="utf-8")
    monkeypatch.setattr("app.api.routes.reports.REPORTS_DIR", report_dir.parent)
    client = TestClient(app)
    response = client.get("/api/reports")
    assert response.json()[0]["asset_type"] == "stocks"


def test_get_reports_normalizes_legacy_report_without_asset_type_or_reports(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import app

    report_dir = tmp_path / "data" / "reports" / "20260403_120000_BTC"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text(json.dumps({
        "symbol": "BTC",
        "timestamp": "2026-04-03T04:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr("app.api.routes.reports.REPORTS_DIR", report_dir.parent)
    client = TestClient(app)
    response = client.get("/api/reports")
    body = response.json()[0]
    assert body["asset_type"] == "crypto"
    assert body["query"] == ""
    assert body["reports"] == {"cio": None, "quant": None, "news": None, "social": None}


def test_get_report_detail_applies_same_normalization(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import app

    report_dir = tmp_path / "data" / "reports" / "20260403_120000_BTC"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text(json.dumps({
        "symbol": "BTC",
        "timestamp": "2026-04-03T04:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr("app.api.routes.reports.REPORTS_DIR", report_dir.parent)
    client = TestClient(app)
    response = client.get("/api/reports/20260403_120000_BTC")
    body = response.json()
    assert body["asset_type"] == "crypto"
    assert body["query"] == ""
    assert body["reports"] == {"cio": None, "quant": None, "news": None, "social": None}
```

- [ ] **Step 2: Run the route tests to verify they fail**

Run: `uv run pytest tests/test_reports_routes.py -q`

Expected:
- FAIL because the schema does not expose `asset_type`
- and/or FAIL because the route returns `query=None` or `reports=None` for legacy files

- [ ] **Step 3: Write the minimal implementation**

```python
# app/api/models/schemas.py
from typing import Literal

class ReportTexts(BaseModel):
    cio: Optional[str] = None
    quant: Optional[str] = None
    news: Optional[str] = None
    social: Optional[str] = None


class Report(BaseModel):
    id: str
    symbol: str
    asset_type: Literal["stocks", "crypto"] = "stocks"
    timestamp: str
    query: str = ""
    final_decision: Optional[str] = None
    quant_analysis: Optional[Dict[str, Any]] = None
    news_sentiment: Optional[Dict[str, Any]] = None
    social_sentiment: Optional[Dict[str, Any]] = None
    reports: ReportTexts = Field(default_factory=ReportTexts)
```

```python
# app/api/routes/reports.py
from app.reporting.asset_type import classify_asset_type
from ..models import Report, ReportTexts


def _build_report_response(report_id: str, data: dict) -> Report:
    symbol = data.get("symbol", "UNKNOWN")
    return Report(
        id=report_id,
        symbol=symbol,
        asset_type=data.get("asset_type") or classify_asset_type(symbol),
        timestamp=data.get("timestamp", ""),
        query=data.get("query") or "",
        final_decision=data.get("final_decision"),
        quant_analysis=data.get("quant_analysis"),
        news_sentiment=data.get("news_sentiment"),
        social_sentiment=data.get("social_sentiment"),
        reports=ReportTexts(**(data.get("reports") or {})),
    )
```

- [ ] **Step 4: Run the route tests and a combined backend regression check**

Run: `uv run pytest tests/test_reports_routes.py tests/test_reporting_asset_type.py tests/test_multi_agent_graph.py -q`

Expected:
- PASS
- both the route contract and aggregated report contract remain green

- [ ] **Step 5: Commit**

```bash
git add app/api/models/schemas.py app/api/routes/reports.py tests/test_reports_routes.py
git commit -m "feat(api): normalize reports contract for real reports page"
```

## Chunk 2: Frontend Integration And Cleanup

### Task 3: Switch the reports UI to the real contract and minimal API rendering

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/reports/ReportCard.tsx`
- Modify: `frontend/src/app/reports/page.tsx`

- [ ] **Step 1: Make the frontend contract change visible and capture the initial failure**

```ts
// frontend/src/lib/types.ts
// Replace the existing ReportTexts definition; do not keep the old optional-key version.
export interface ReportTexts {
  cio: string | null;
  quant: string | null;
  news: string | null;
  social: string | null;
}

export interface Report {
  id: string;
  symbol: string;
  asset_type: "stocks" | "crypto";
  timestamp: string;
  query: string;
  final_decision?: string;
  quant_analysis?: QuantAnalysis;
  news_sentiment?: NewsSentiment;
  social_sentiment?: SocialSentiment;
  reports: ReportTexts;
}
```

```tsx
// frontend/src/components/reports/ReportCard.tsx
import type { Report } from "@/lib/types";

interface ReportCardProps {
  report: Report;
}

// Keep the old access temporarily so the red phase is guaranteed:
<Badge variant="outline" className="text-xs">
  {report.assetType}
</Badge>
```

This intentionally leaves the stale `report.assetType` access in place for one run so the compiler has a guaranteed failure.

Run:

`pnpm --dir frontend type-check`

Expected:
- FAIL because `Property 'assetType' does not exist on type 'Report'`
- and/or FAIL because `mockReports` no longer matches the stricter real `Report` shape

- [ ] **Step 2: Implement the minimal real-data page and safe card rendering**

```tsx
// frontend/src/app/reports/page.tsx
"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Report } from "@/lib/types";
import { Accordion } from "@/components/ui/accordion";
import { ReportCard } from "@/components/reports/ReportCard";

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  async function loadReports() {
    try {
      const data = await api.getReports();
      setReports([...data].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp)));
    } catch (error) {
      console.error("Failed to load reports", error);
      setReports([]);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadReports();
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Analysis Reports</h1>
        <p className="mt-2 text-muted-foreground">
          Browse all generated financial analysis reports
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading reports...</p>
      ) : reports.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <p className="text-muted-foreground">
            No analyses yet. Run your first analysis from the main page.
          </p>
        </div>
      ) : (
        <Accordion type="multiple" className="flex flex-col gap-4">
          {reports.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </Accordion>
      )}
    </div>
  );
}
```

```tsx
// frontend/src/components/reports/ReportCard.tsx
const summary =
  markdownSummary(report.reports.cio ?? "", 200) || "No summary available.";

<Badge variant="outline" className="text-xs">
  {report.asset_type}
</Badge>
<p className="truncate text-sm text-foreground">
  {report.query || "No query available."}
</p>
```

This task is complete when the page no longer imports `mockReports`, fetches once on entry, sorts by descending timestamp, and renders the real list without refresh/loading polish yet.

- [ ] **Step 3: Run frontend static verification for the minimal real-data version**

Run:
- `pnpm --dir frontend type-check`
- `pnpm --dir frontend lint`

Expected:
- PASS
- no remaining type references to the mock-only `AnalysisReport`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/components/reports/ReportCard.tsx frontend/src/app/reports/page.tsx
git commit -m "feat(frontend): wire reports page to backend data"
```

### Task 4: Add skeleton and manual refresh behavior

**Files:**
- Create: `frontend/src/components/reports/ReportsListSkeleton.tsx`
- Modify: `frontend/src/app/reports/page.tsx`

- [ ] **Step 1: Introduce the UI references first so the next type-check must fail**

Add the render branches and button usage before the helper component exists:

```tsx
// frontend/src/app/reports/page.tsx
"use client";

import { useState } from "react";
import { RefreshCwIcon } from "lucide-react";
import type { Report } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { ReportsListSkeleton } from "@/components/reports/ReportsListSkeleton";

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  if (isLoading) {
    return <ReportsListSkeleton />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Analysis Reports</h1>
          <p className="mt-2 text-muted-foreground">
            Browse all generated financial analysis reports
          </p>
        </div>
        <Button onClick={() => void loadReports(true)} disabled={isLoading || isRefreshing}>
          <RefreshCwIcon data-icon="inline-start" />
          Refresh
        </Button>
      </div>
    </div>
  );
}
```

Run:

`pnpm --dir frontend type-check`

Expected:
- FAIL because `ReportsListSkeleton` and `loadReports(true)` are referenced before implementation

- [ ] **Step 2: Implement the loading, empty-state, and refresh branches**

```tsx
// frontend/src/components/reports/ReportsListSkeleton.tsx
import { Skeleton } from "@/components/ui/skeleton";

export function ReportsListSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      {Array.from({ length: 3 }).map((_, index) => (
        <Skeleton key={index} className="h-24 w-full rounded-lg" />
      ))}
    </div>
  );
}
```

```tsx
// frontend/src/app/reports/page.tsx
"use client";

import { useEffect, useState } from "react";
import { RefreshCwIcon } from "lucide-react";
import { api } from "@/lib/api";
import type { Report } from "@/lib/types";
import { ReportCard } from "@/components/reports/ReportCard";
import { ReportsListSkeleton } from "@/components/reports/ReportsListSkeleton";
import { Accordion } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  async function loadReports(refresh: boolean) {
    try {
      refresh ? setIsRefreshing(true) : setIsLoading(true);
      const data = await api.getReports();
      setReports([...data].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp)));
    } catch (error) {
      console.error("Failed to load reports", error);
      setReports([]);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    void loadReports(false);
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Analysis Reports</h1>
          <p className="mt-2 text-muted-foreground">
            Browse all generated financial analysis reports
          </p>
        </div>
        <Button onClick={() => void loadReports(true)} disabled={isLoading || isRefreshing}>
          <RefreshCwIcon
            data-icon="inline-start"
            className={isRefreshing ? "animate-spin" : undefined}
          />
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <ReportsListSkeleton />
      ) : reports.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <p className="text-muted-foreground">
            No analyses yet. Run your first analysis from the main page.
          </p>
        </div>
      ) : (
        <Accordion type="multiple" className="flex flex-col gap-4">
          {reports.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </Accordion>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run frontend verification with the final UX behavior**

Run:
- `pnpm --dir frontend type-check`
- `pnpm --dir frontend lint`

Expected:
- PASS
- initial load shows skeletons, refresh button is rendered, and the button is disabled while refresh is in flight

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/reports/ReportsListSkeleton.tsx frontend/src/app/reports/page.tsx
git commit -m "feat(frontend): add reports refresh and loading states"
```

### Task 5: Remove dead reports scaffolding and run final verification

**Files:**
- Delete: `frontend/src/app/reports/[id]/page.tsx`
- Delete: `frontend/src/lib/mock-data/reports.ts`

- [ ] **Step 1: Delete the dead files after confirming there are no remaining imports**

Run:
- `rg -n "mock-data/reports|mockReports|AnalysisReport|assetType" frontend/src`

Expected:
- Only the legacy references you are about to remove appear

Then delete:
- `frontend/src/app/reports/[id]/page.tsx`
- `frontend/src/lib/mock-data/reports.ts`

- [ ] **Step 2: Run the focused backend tests and frontend verification together**

Run:
- `uv run pytest tests/test_multi_agent_graph.py tests/test_reports_routes.py tests/test_reporting_asset_type.py -q`
- `pnpm --dir frontend type-check`
- `pnpm --dir frontend lint`

Optional if the route/page boundary needs one more check:
- `pnpm --dir frontend build`

Expected:
- PASS for all required commands
- optional build passes if run

- [ ] **Step 3: Commit**

```bash
git add -A frontend/src/app/reports frontend/src/lib/mock-data/reports.ts
git commit -m "chore(frontend): remove obsolete reports scaffolding"
```
