# Analysis Progress Streaming Design

**Problem**

The current homepage analysis flow still behaves like a black box. The frontend opens `/api/analyze/stream`, but the backend waits for `run_once()` to finish before emitting a single final result. Users therefore see little or no credible evidence that the system is actively fetching market data, calling MCP-backed tools, analyzing news, or processing Reddit discussion while a long-running analysis is in progress.

At the same time, the product must not expose raw LLM reasoning or chain-of-thought style material. The user should see trustworthy operational telemetry such as stage progress, tool-call summaries, and concise fetch results, while private decision traces remain stored in the backend for future LLM-only reflection and post-run learning.

**Goal**

Add real-time `Analysis Progress` visibility to the homepage analysis experience by streaming sanitized stage and tool telemetry over SSE, rendering a mixed progress UI on the current analysis page, and persisting private LLM decision traces in the backend database without exposing them to users or changing `/reports`.

**Design**

## Scope

- Replace the current pseudo-streaming `/api/analyze/stream` behavior with true incremental SSE updates during analysis execution.
- Show a mixed progress UI on the homepage analysis panel:
  - top-level stage cards for `Quant`, `News`, `Social`, and `CIO`
  - a real-time event feed for tool calls, fetch summaries, and stage completion
  - the final `CIO` report only after the run completes
- Standardize all user-visible runtime updates into a single public event schema so the frontend never parses backend-internal objects directly.
- Introduce a thread-safe runtime bridge that allows synchronous worker code and thread-pool tasks to emit events into the async SSE response stream.
- Persist private LLM decision materials in the backend database for later LLM-only reflection workflows.
- Keep `/reports` and all existing historical report views unchanged.

## Non-Goals

- Do not expose chain-of-thought, intermediate drafts, rejected alternatives, or internal prompts in the UI.
- Do not add event replay or history playback to `/reports`.
- Do not display partial `Quant`, `News`, or `Social` markdown reports in the homepage while the run is still executing.
- Do not migrate this feature to WebSockets; SSE remains the transport.
- Do not redesign the broader site layout outside the existing homepage analysis panel.

## User-Facing Behavior

### Homepage Analysis Panel

When the user submits a query from the homepage:

1. The right-side analysis panel switches into an `Analysis Progress` view.
2. Four stage cards appear for:
   - `Quant`
   - `News`
   - `Social`
   - `CIO`
3. Each stage moves through `pending`, `running`, `completed`, or `failed`.
4. Below the cards, a real-time event feed appends short operational updates such as:
   - `Calling realtime news search`
   - `Fetched 8 news articles from Tavily`
   - `Fetched 23 Reddit posts and 184 comments`
   - `ML quant analysis completed`
   - `CIO synthesis started`
5. The event feed auto-scrolls while still allowing the user to inspect earlier entries.
6. The final `CIO` markdown report appears only after the overall run completes.
7. If a stage or tool call fails, the relevant stage card switches to `failed`, the event feed records the failure, and the panel shows a clear terminal error state.

### Copy and Terminology

- The UI concept is `Analysis Progress`.
- Existing English product copy should remain consistent with the rest of the frontend.
- The UI must not label anything as `thinking process`.
- User-visible events are framed as execution telemetry, not private reasoning.

## Chosen Architecture

The recommended architecture is:

1. Internal modules emit rich runtime events locally.
2. A runtime bridge normalizes those events into a stable public schema for SSE.
3. Private reasoning is captured separately and stored in the backend database.
4. The frontend consumes only the public schema and renders a mixed progress view with local reducer state.

This design preserves backend flexibility while protecting the frontend from implementation churn.

## Backend Runtime Model

### New Runtime Coordinator

Add a dedicated runtime coordination module, for example `app/analysis/runtime.py`, that owns per-run execution state.

Core responsibilities:

- assign `run_id`, `event_id`, and per-run sequence numbers
- accept events from worker threads and synchronous report-generation code
- normalize public telemetry into a stable schema
- enqueue public events into the async SSE stream
- persist private LLM reasoning payloads to the backend database
- optionally persist public telemetry for backend diagnostics without exposing it through product routes
- guard the SSE bridge lifecycle so late worker-thread emissions cannot crash a run after the request stream has already closed

Representative API surface:

- `emit_stage(stage, status, message, data=None)`
- `emit_tool_call(stage, tool_name, message, data=None)`
- `emit_tool_result(stage, tool_name, message, data=None)`
- `emit_result(payload)`
- `emit_error(stage, message, data=None)`
- `record_private_reasoning(stage, agent_type, payload)`

The runtime object must be optional so existing call sites can continue to function in non-streaming contexts.

### Runtime Lifecycle and Loop Safety

The runtime must defensively manage the event-loop bridge because worker threads may still be running while the request-level SSE response is winding down.

Required behavior:

- store the request loop reference only for the lifetime of the active stream
- maintain an internal `closed` or `terminal` flag once the SSE stream reaches a terminal state
- treat `loop.call_soon_threadsafe(...)` failures after stream shutdown as non-fatal
- wrap thread-originated enqueue attempts so `RuntimeError` from a closed loop is converted into a backend log entry instead of crashing worker execution
- ensure terminal events are emitted at most once

This matters because the current analysis flow uses thread pools for parallel stage execution, and late emissions from `Quant`, `News`, or `Social` must not tear down the whole request if the stream has already ended due to disconnect or terminal completion.

### Public Event Schema

All SSE payloads should conform to one normalized shape.

```json
{
  "event_id": "evt_000012",
  "sequence": 12,
  "run_id": "20260408_101530_NVDA",
  "timestamp": "2026-04-08T10:15:31Z",
  "type": "tool_result",
  "stage": "news",
  "status": "completed",
  "message": "Fetched 8 news articles from Tavily",
  "data": {
    "tool": "search_realtime_news",
    "provider": "tavily",
    "article_count": 8
  }
}
```

Public event fields:

- `event_id`: stable per-event identifier
- `sequence`: monotonic per-run ordering number
- `run_id`: current analysis run id
- `timestamp`: UTC ISO-8601 timestamp
- `type`: one of:
  - `stage`
  - `tool_call`
  - `tool_result`
  - `result`
  - `error`
  - `heartbeat`
- `stage`: one of:
  - `system`
  - `quant`
  - `news`
  - `social`
  - `cio`
- `status`: one of:
  - `pending`
  - `running`
  - `completed`
  - `failed`
- `message`: user-facing human-readable summary
- `data`: structured summary payload with only sanitized fields

### Privacy Boundary

The runtime coordinator must enforce a hard boundary:

- `public telemetry`
  - safe for SSE
  - safe for frontend rendering
  - limited to execution status, tool metadata, counts, providers, durations, and result availability
- `private reasoning`
  - never emitted over SSE
  - never attached to frontend response objects
  - never surfaced in `/reports`
  - stored only for backend LLM reflection workflows

Disallowed from public events:

- raw or summarized chain-of-thought
- full prompts
- rejected hypotheses
- draft recommendations
- raw large corpora from news or Reddit ingestion
- reflection notes meant only for internal model learning

## Streaming Execution Flow

### Analyze Route

`app/api/routes/analyze.py` should stop waiting for the full analysis to finish before producing output.

Instead:

1. Create an `AnalysisRuntime` instance.
2. Create an `asyncio.Queue` for public SSE events.
3. Start the actual analysis in a background thread.
4. Let the runtime push normalized public events into the queue using `loop.call_soon_threadsafe(...)`.
5. Stream events as they arrive.
6. End the stream only after a terminal `result` or `error` event.

The route should also emit a lightweight `heartbeat` event if no progress events arrive for a small interval, so long-running external fetches do not look frozen.

If the client disconnects or the response terminates early, the runtime should mark the public stream as closed. Worker threads may continue best-effort backend persistence, but they must stop assuming that enqueueing into the loop will succeed.

### Graph Entry Points

Extend the analysis entry points to accept an optional runtime object:

- `run_once(user_input: str, runtime: AnalysisRuntime | None = None)`
- `_parallel_runner(state, runtime=...)`
- `_cio_node(state, runtime=...)`
- `generate_quant_report(..., runtime=None)`
- `generate_news_report(..., runtime=None)`
- `generate_social_report(..., runtime=None)`

The runtime parameter should be threaded through without changing non-streaming semantics.

## Instrumentation Points

### System and Graph Level

Emit high-level stage events for:

- run accepted
- parallel fan-out started
- `Quant`, `News`, and `Social` tasks dispatched
- `CIO` synthesis started
- overall run completed or failed

### Quant Stage

Instrument `app/quant/generate_report.py` around:

- local indicator fetch start and completion
- indicator source identification
- ML quant analysis start and completion
- quant report bundle completion

Example public telemetry:

- `Loading 90-day local technical snapshot`
- `Loaded technical snapshot from local database`
- `Running ML quant analysis`
- `Quant report completed`

Private reasoning capture may store:

- LLM summarization prompt/response metadata for `_summarize_quant_snapshot`
- any future CIO-facing quant rationale not intended for users

### News Stage

Instrument `app/news/generate_report.py` around:

- realtime news search start
- news provider chosen and article count returned
- Polymarket fetch start and completion
- LLM news analysis start and completion
- report bundle completion

Example public telemetry:

- `Calling realtime news search`
- `Fetched 8 news articles from Tavily`
- `Fetching Polymarket signals`
- `News sentiment report completed`

### Social Stage

Instrument `app/social/generate_report.py` around:

- Reddit fetch start
- ingestion counts
- NLP analysis start and completion
- report bundle completion

Example public telemetry:

- `Fetching Reddit discussion`
- `Fetched 23 posts and 184 comments`
- `Running social sentiment analysis`
- `Social report completed`

### CIO Stage

Instrument `app/graph_multi.py::_cio_node` around:

- CIO synthesis start
- final markdown decision generated
- final aggregate report persisted

The public feed should show only execution status and completion. Private database storage should capture any CIO-internal decision-chain material needed for later LLM reflection.

## Database Persistence

### Existing Tables

`analysis_runs` should remain the source of truth for run identity, query, asset, and final decision.

The existing `agent_executions` and `tool_calls` tables are useful but do not currently model:

- normalized run-level progress telemetry
- private LLM-only reasoning payloads separated from user-safe events

### New Internal Tables

Extend `app/database/agent_history.py` with internal-only tables such as:

#### `analysis_progress_events`

Purpose:

- store normalized public telemetry for debugging, audits, and future internal replay
- remain unavailable to current product routes

Suggested columns:

- `event_id TEXT PRIMARY KEY`
- `run_id TEXT NOT NULL`
- `sequence INTEGER NOT NULL`
- `stage TEXT NOT NULL`
- `event_type TEXT NOT NULL`
- `status TEXT NOT NULL`
- `message TEXT NOT NULL`
- `data_json TEXT`
- `timestamp DATETIME NOT NULL`

#### `analysis_private_reasoning`

Purpose:

- store LLM-only decision traces and reflection material
- never exposed to users

Suggested columns:

- `reasoning_id TEXT PRIMARY KEY`
- `run_id TEXT NOT NULL`
- `stage TEXT NOT NULL`
- `agent_type TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `created_at DATETIME NOT NULL`

The spec intentionally keeps these tables internal-only. No new report or history API route should expose them in this feature.

### Threading and Connection Discipline

This repository currently uses direct `sqlite3` helpers in `app/database/agent_history.py`, not a shared ORM session or SQLAlchemy connection pool. The implementation must therefore avoid transplanting generic ORM guidance into the codebase.

Required rules:

- do not share a single `sqlite3.Connection`, cursor, or transaction object across worker threads
- keep database writes thread-safe by opening and closing connections inside each persistence helper call, matching the existing repository pattern
- keep writes short-lived and append-oriented so the thread pool is not blocked on long database transactions
- if write frequency becomes a bottleneck later, introduce a dedicated persistence queue or writer thread as a follow-up optimization rather than prematurely adding a new ORM layer in this feature

For this feature, correctness matters more than pooling sophistication. The runtime should reuse repository-local helper functions or extend them, but it must not create a cross-thread shared database handle for `analysis_progress_events` or `analysis_private_reasoning`.

### Private Reasoning Payload Contract

Even though private reasoning is stored in `payload_json`, the backend should not treat that field as an unstructured string blob.

Add a typed backend contract, such as a `TypedDict` or Pydantic model, that validates a versioned reasoning envelope before persistence. A representative shape is:

```json
{
  "schema_version": 1,
  "reasoning_kind": "cio_synthesis",
  "model": "gpt-5.x",
  "prompt": "...",
  "raw_completion": "...",
  "parsed_summary": {
    "decision": "bullish",
    "confidence": "medium"
  },
  "tool_context": {
    "quant_available": true,
    "news_available": true,
    "social_available": false
  }
}
```

The exact fields may vary by stage, but the contract should be explicit and versioned so later LLM reflection jobs do not depend on ad hoc JSON cleanup. The implementation should validate these payloads before insert and reject malformed internal records early.

## Frontend State Model

### State Strategy

Do not introduce Zustand in this change.

Instead:

- create a reusable analysis-session state module under a focused frontend feature directory such as `frontend/src/features/analysis-session/`
- implement a pure `useReducer` state machine for:
  - stage statuses
  - normalized event list
  - connection state
  - final result payload
  - terminal error state
- use React 19 low-priority updates for high-frequency event appends so the input area remains responsive

This keeps the current feature local to the homepage while still making the reducer reusable if a global store becomes justified later.

### Reducer Shape

Representative session state:

```ts
type StageKey = "quant" | "news" | "social" | "cio";

interface AnalysisSessionState {
  runId: string | null;
  connection: "idle" | "connecting" | "streaming" | "completed" | "failed";
  stages: Record<StageKey, { status: "pending" | "running" | "completed" | "failed"; message: string | null }>;
  events: AnalysisEvent[];
  finalResult: { final_decision?: string } | null;
  error: string | null;
}
```

Reducer actions should be derived directly from normalized SSE events so the UI state is fully replayable from the event stream.

## Frontend UI Structure

### Homepage Only

Keep the homepage layout intact and confine the new experience to the existing right-side analysis panel.

### Component Decomposition

The current `ChatPanel` should become a thin session container that composes smaller UI units such as:

- `AnalysisStageCards`
- `AnalysisEventFeed`
- `AnalysisFinalReport`
- `AnalysisComposer` or the existing input form

Responsibilities:

- `ChatPanel`
  - open and close SSE connection
  - dispatch normalized events into reducer state
  - render idle, running, completed, and failed states
- `AnalysisStageCards`
  - render four stable stage cards with status badges
- `AnalysisEventFeed`
  - render the running event timeline, auto-scroll behavior, and compact event metadata
- `AnalysisFinalReport`
  - render only the final `CIO` markdown after completion

### Visual Behavior

- stage cards remain visible throughout the run
- event feed grows incrementally below them
- final report replaces the empty/filler content only once available
- no partial `Quant`, `News`, or `Social` markdown tabs are shown in this iteration

## API and Type Surface

### Backend Models

Add explicit event models for the public schema so backend responses are typed and testable. These can live beside existing API models or in a dedicated analysis-events module.

### Frontend Types

Replace the current loose `SSEEvent` type with a discriminated union matching the normalized public schema. Avoid leaving the frontend on a `message?: string` plus `data?: unknown` contract.

This is important because the stage cards and event feed should rely on exact event types rather than ad hoc string inspection.

## Error Handling

- any stage-level failure emits a terminal `error` event
- frontend closes the SSE stream on terminal `result` or `error`
- connection loss before a terminal event should surface a clear `Connection lost` error state
- heartbeats should not be rendered as user-facing log entries
- private reasoning persistence failure must not leak payloads; it should degrade safely into a backend log entry while allowing the analysis run to continue if possible

## Testing Strategy

### Backend Tests

- unit tests for event normalization and monotonic sequencing
- unit tests that public events reject private reasoning payloads
- unit tests that runtime emissions from worker threads are delivered to the async queue in order
- route tests for `/api/analyze/stream` that verify:
  - at least one progress event arrives before the final result
  - terminal result closes the stream
  - terminal error closes the stream
- database tests for creation and insertion of:
  - `analysis_progress_events`
  - `analysis_private_reasoning`

### Frontend Tests

- reducer tests for:
  - stage transitions
  - event append ordering
  - final result storage
  - terminal error handling
- component-level tests for:
  - stage cards reflecting reducer state
  - event feed hiding `heartbeat`
  - final CIO markdown rendering only after completion

Tests should prefer pure-function coverage where possible because the reducer and selectors are the core contract.

## File and Responsibility Map

Likely files touched:

- Backend
  - create: `app/analysis/runtime.py`
  - create: `app/api/models/analysis_events.py` or equivalent
  - modify: `app/api/routes/analyze.py`
  - modify: `app/graph_multi.py`
  - modify: `app/quant/generate_report.py`
  - modify: `app/news/generate_report.py`
  - modify: `app/social/generate_report.py`
  - modify: `app/database/agent_history.py`
- Frontend
  - create: `frontend/src/features/analysis-session/types.ts`
  - create: `frontend/src/features/analysis-session/reducer.ts`
  - create: `frontend/src/features/analysis-session/selectors.ts`
  - create: focused UI components under `frontend/src/components/chat/`
  - modify: `frontend/src/components/chat/ChatPanel.tsx`
  - modify: `frontend/src/components/chat/ResultCard.tsx` or replace it with narrower components
  - modify: `frontend/src/lib/api.ts`
  - modify: `frontend/src/lib/types.ts`

## Risks

- emitting too many tiny events could flood the UI and reduce readability
- mixing private and public event payloads in the same interface would create a privacy footgun
- thread-to-async queue bridging can introduce ordering bugs if sequencing is not centralized
- backend instrumentation that lives too close to tool internals may become brittle if tools are swapped later

## Mitigations

- keep public events summary-oriented and cap noisy event categories
- enforce a dedicated normalization boundary inside the runtime coordinator
- assign per-run sequence numbers only inside the runtime coordinator
- instrument stable stage boundaries and report-generation seams rather than every internal helper

## Acceptance Criteria

The feature is complete when all of the following are true:

1. Homepage analysis shows real incremental `Analysis Progress` instead of waiting for the final result.
2. Users can see stage status and tool/fetch summaries for `Quant`, `News`, `Social`, and `CIO`.
3. The homepage shows only the final `CIO` report body, not partial sub-report markdown tabs.
4. `/reports` remains unchanged.
5. User-visible SSE events never expose private LLM reasoning.
6. Private LLM decision traces are persisted in the backend database for internal-only use.
7. The frontend consumes a typed normalized event schema rather than backend-specific raw payloads.
