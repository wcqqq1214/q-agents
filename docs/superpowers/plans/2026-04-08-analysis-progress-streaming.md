# Analysis Progress Streaming Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add true incremental analysis progress streaming to the homepage by emitting sanitized SSE events from the backend, rendering stage cards plus a real-time event feed in the frontend, and persisting private LLM reasoning in internal-only database tables.

**Architecture:** Introduce a reusable backend runtime coordinator that normalizes public events, bridges worker-thread emissions into the async SSE response, and stores private reasoning separately. Keep the homepage UI local to `ChatPanel`, but move session logic into a reusable reducer/selectors module so the event contract is typed, replayable, and decoupled from presentation.

**Tech Stack:** FastAPI, asyncio, sqlite3, LangGraph, Python 3.13 via `uv`, Next.js 16, React 19, TypeScript, Node built-in test runner, ESLint, TypeScript strict mode

---

## File Structure

### Backend units

- `app/analysis/runtime.py`
  - Per-run runtime coordinator.
  - Owns public event normalization, sequence assignment, loop-safe queue bridging, and private reasoning persistence hooks.
- `app/analysis/__init__.py`
  - Re-export runtime types for cleaner imports.
- `app/api/models/analysis_events.py`
  - Public typed event models and result payload shapes for SSE.
- `app/api/models/__init__.py`
  - Export new event models.
- `app/api/routes/analyze.py`
  - Build the async streaming loop around `AnalysisRuntime`.
  - Emit terminal `result`/`error` events and heartbeat handling.
- `app/graph_multi.py`
  - Thread the optional runtime through `run_once`, `_parallel_runner`, and `_cio_node`.
  - Emit system/stage-level events.
- `app/quant/generate_report.py`
  - Emit quant stage tool and completion events.
  - Capture private reasoning for quant summarization if available.
- `app/news/generate_report.py`
  - Emit news tool-call and tool-result summaries.
  - Capture internal-only LLM analysis payloads.
- `app/social/generate_report.py`
  - Emit Reddit fetch/NLP summary events.
- `app/database/agent_history.py`
  - Create internal-only tables for public progress events and private reasoning.
  - Add persistence helpers for both tables.

### Backend tests

- `tests/test_agent_history.py`
  - Extend for new internal-only tables and persistence helpers.
- `tests/test_analysis_runtime.py`
  - New unit tests for event normalization, loop shutdown safety, and terminal sequencing.
- `tests/test_analysis_stage_events.py`
  - New stage-level tests for quant/news/social/CIO instrumentation using monkeypatched tools and LLM calls.
- `tests/test_analyze_routes.py`
  - Update route tests to assert real progress arrives before the final result.

### Frontend units

- `frontend/src/features/analysis-session/types.ts`
  - Public frontend event and session-state types derived from the SSE schema.
- `frontend/src/features/analysis-session/reducer.ts`
  - Pure reducer for stage status, visible events, final result, and errors.
- `frontend/src/features/analysis-session/selectors.ts`
  - Derived selectors that hide heartbeat events and shape card/feed props.
- `frontend/src/features/analysis-session/reducer.test.ts`
  - Pure Node tests for state transitions.
- `frontend/src/components/chat/AnalysisStageCards.tsx`
  - Top stage-card strip for Quant/News/Social/CIO.
- `frontend/src/components/chat/AnalysisEventFeed.tsx`
  - Real-time visible event list.
- `frontend/src/components/chat/AnalysisFinalReport.tsx`
  - Final CIO markdown renderer.
- `frontend/src/components/chat/AnalysisProgress.test.ts`
  - Source-level regression checks for new chat progress UI wiring and copy.
- `frontend/src/components/chat/ChatPanel.tsx`
  - Session container that manages `EventSource`, reducer dispatch, and terminal states.
- `frontend/src/components/chat/ResultCard.tsx`
  - Outer card shell that composes the new progress subcomponents.
- `frontend/src/lib/api.ts`
  - Typed `EventSource` helper unchanged in transport, but aligned with new event contract.
- `frontend/src/lib/types.ts`
  - Remove the old loose SSE event shape or narrow it to re-export frontend session types.

---

## Chunk 1: Backend Runtime Contracts and Persistence

### Task 1: Add runtime and persistence tests, then implement the internal event store

**Files:**
- Create: `app/analysis/__init__.py`
- Create: `app/analysis/runtime.py`
- Create: `app/api/models/analysis_events.py`
- Modify: `app/api/models/__init__.py`
- Modify: `app/database/agent_history.py`
- Modify: `tests/test_agent_history.py`
- Create: `tests/test_analysis_runtime.py`

- [ ] **Step 1: Write the failing database and runtime tests**

Add tests that prove all of the following before production code changes:

```python
def test_init_db_creates_progress_and_private_reasoning_tables(tmp_path: Path) -> None:
    init_db(str(tmp_path / "history.db"))
    # assert new tables exist

def test_save_analysis_progress_event_round_trips_json_payload(tmp_path: Path) -> None:
    # save event, assert sequence/message/data_json persist

def test_save_private_reasoning_persists_versioned_payload(tmp_path: Path) -> None:
    payload = {"schema_version": 1, "reasoning_kind": "cio_synthesis"}
    # save and assert JSON round-trip

def test_runtime_drops_late_loop_emissions_after_close() -> None:
    # closed runtime should not crash on late enqueue attempt

def test_runtime_emits_terminal_event_only_once() -> None:
    # duplicate terminal emissions are ignored
```

- [ ] **Step 2: Run the new focused backend tests and verify they fail**

Run: `uv run pytest tests/test_agent_history.py tests/test_analysis_runtime.py -q`
Expected: FAIL because the new tables, helpers, models, and runtime module do not exist yet.

- [ ] **Step 3: Implement the database helpers, event models, and runtime coordinator**

Implement:

```python
class AnalysisRuntime:
    def emit_stage(self, stage: str, status: str, message: str, data: dict[str, Any] | None = None) -> None: ...
    def emit_tool_call(self, stage: str, tool_name: str, message: str, data: dict[str, Any] | None = None) -> None: ...
    def emit_tool_result(self, stage: str, tool_name: str, message: str, data: dict[str, Any] | None = None) -> None: ...
    def emit_result(self, payload: dict[str, Any]) -> None: ...
    def emit_error(self, stage: str, message: str, data: dict[str, Any] | None = None) -> None: ...
    def record_private_reasoning(self, stage: str, agent_type: str, payload: PrivateReasoningPayload) -> None: ...
```

Implementation requirements:
- centralize sequence assignment in `AnalysisRuntime`
- use a closed/terminal guard around loop bridging
- catch `RuntimeError` from late `call_soon_threadsafe(...)` and degrade to logging
- create `analysis_progress_events` and `analysis_private_reasoning` tables in `init_db`
- keep sqlite writes short-lived by opening and closing a connection per helper call
- validate a versioned private reasoning envelope before writing `payload_json`

- [ ] **Step 4: Re-run the focused backend tests and verify they pass**

Run: `uv run pytest tests/test_agent_history.py tests/test_analysis_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/analysis/__init__.py app/analysis/runtime.py app/api/models/analysis_events.py app/api/models/__init__.py app/database/agent_history.py tests/test_agent_history.py tests/test_analysis_runtime.py
git commit -m "feat(api): add analysis runtime event contracts"
```

### Task 2: Convert `/api/analyze/stream` into a true incremental SSE endpoint

**Files:**
- Modify: `app/api/routes/analyze.py`
- Modify: `tests/test_analyze_routes.py`
- Modify: `tests/test_analysis_runtime.py`

- [ ] **Step 1: Write failing route tests for incremental streaming**

Extend the route tests so the stream must yield progress before the final result:

```python
def test_stream_emits_progress_before_final_result(client: TestClient) -> None:
    # patch run_once to call runtime.emit_stage(...) before returning final result
    # collect SSE events, assert first non-heartbeat event is progress/stage/tool_call
    # assert final result still includes CIO markdown

def test_stream_emits_error_event_when_background_run_fails(client: TestClient) -> None:
    # patch run_once to raise after a partial event sequence
```

Also add a runtime-oriented unit test for heartbeat formatting or terminal-stream closure if it fits better in `tests/test_analysis_runtime.py`.

- [ ] **Step 2: Run the route tests and verify they fail**

Run: `uv run pytest tests/test_analyze_routes.py tests/test_analysis_runtime.py -q`
Expected: FAIL because `/api/analyze/stream` still waits for `run_once()` to finish before emitting anything.

- [ ] **Step 3: Implement the async queue bridge in `app/api/routes/analyze.py`**

Refactor the route to:

```python
async def run_analysis_stream(query: str) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    runtime = AnalysisRuntime.for_stream(loop=asyncio.get_running_loop(), queue=queue)
    task = asyncio.create_task(asyncio.to_thread(run_once, query, runtime))
    # yield queue events incrementally
```

Implementation requirements:
- initialize `AnalysisRuntime` with the request loop and a public-event callback/queue sink
- emit a heartbeat only when the queue stays idle past the configured interval
- close the stream only after one terminal `result` or `error`
- mark runtime public streaming as closed if the client disconnects
- keep the non-streaming `POST /api/analyze` behavior unchanged for now

- [ ] **Step 4: Re-run the route tests and verify they pass**

Run: `uv run pytest tests/test_analyze_routes.py tests/test_analysis_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/analyze.py tests/test_analyze_routes.py tests/test_analysis_runtime.py
git commit -m "feat(api): stream incremental analysis progress events"
```

## Chunk 2: Backend Stage Instrumentation

### Task 3: Instrument Quant and News stages with sanitized public telemetry

**Files:**
- Modify: `app/graph_multi.py`
- Modify: `app/quant/generate_report.py`
- Modify: `app/news/generate_report.py`
- Create: `tests/test_analysis_stage_events.py`

- [ ] **Step 1: Write failing stage instrumentation tests for Quant and News**

Create monkeypatched unit tests that avoid real network/LLM calls:

```python
def test_quant_report_emits_indicator_and_ml_events(monkeypatch: pytest.MonkeyPatch) -> None:
    # patch get_local_stock_data.invoke and run_ml_quant_analysis.invoke
    # assert runtime captured quant tool_call/tool_result/stage completion events

def test_news_report_emits_news_fetch_and_polymarket_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    # patch search_realtime_news.invoke, search_polymarket_predictions.invoke, create_llm
    # assert provider/article_count summary event is emitted
```

- [ ] **Step 2: Run the new stage tests and verify they fail**

Run: `uv run pytest tests/test_analysis_stage_events.py -q`
Expected: FAIL because the report generators do not accept or use a runtime yet.

- [ ] **Step 3: Thread runtime into graph fan-out, quant, and news report generation**

Implementation outline:

```python
def generate_report(asset: str, run_dir: str, runtime: AnalysisRuntime | None = None) -> NewsBundle:
    runtime.emit_stage("news", "running", "Calling realtime news search")
    # emit_tool_call / emit_tool_result around search and Polymarket fetch
```

Required behavior:
- `_parallel_runner` emits dispatch/start events for `quant`, `news`, and `social`
- quant emits start/result events for local indicators and ML analysis
- news emits start/result events for news search and Polymarket fetch
- any public event payload includes only safe counts/provider metadata, not raw corpora or reasoning text
- quant/news internal LLM payloads may be written through `record_private_reasoning(...)`

- [ ] **Step 4: Re-run the stage tests and verify they pass**

Run: `uv run pytest tests/test_analysis_stage_events.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/graph_multi.py app/quant/generate_report.py app/news/generate_report.py tests/test_analysis_stage_events.py
git commit -m "feat(progress): instrument quant and news stage events"
```

### Task 4: Instrument Social and CIO stages, then verify terminal event sequencing

**Files:**
- Modify: `app/graph_multi.py`
- Modify: `app/social/generate_report.py`
- Modify: `tests/test_analysis_stage_events.py`
- Modify: `tests/test_analyze_routes.py`

- [ ] **Step 1: Add failing tests for Social/CIO progress and final event ordering**

Extend the stage and route tests:

```python
def test_social_report_emits_fetch_and_nlp_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    # patch reddit fetch + NLP + social report build

def test_cio_emits_stage_start_then_terminal_result(client: TestClient) -> None:
    # assert stage events precede the terminal result event
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/test_analysis_stage_events.py tests/test_analyze_routes.py -q`
Expected: FAIL because Social and CIO do not emit the required events yet.

- [ ] **Step 3: Implement Social and CIO instrumentation**

Implementation requirements:
- social emits:
  - Reddit fetch start
  - fetched post/comment summary
  - NLP completion
  - stage completion
- CIO emits:
  - synthesis start
  - final markdown generated
  - terminal `result`
- terminal `result` remains the only event that contains the user-facing final report payload
- private CIO reasoning, if captured, goes only to `analysis_private_reasoning`

- [ ] **Step 4: Re-run the focused tests and verify they pass**

Run: `uv run pytest tests/test_analysis_stage_events.py tests/test_analyze_routes.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/graph_multi.py app/social/generate_report.py tests/test_analysis_stage_events.py tests/test_analyze_routes.py
git commit -m "feat(progress): instrument social and cio stage events"
```

## Chunk 3: Frontend Session State and UI

### Task 5: Add a typed analysis-session reducer with Node-based regression tests

**Files:**
- Create: `frontend/src/features/analysis-session/types.ts`
- Create: `frontend/src/features/analysis-session/reducer.ts`
- Create: `frontend/src/features/analysis-session/selectors.ts`
- Create: `frontend/src/features/analysis-session/reducer.test.ts`

- [ ] **Step 1: Write the failing reducer tests**

Create pure Node tests covering the event contract:

```ts
test("stage event moves a stage from pending to running", () => {
  const next = reduceAnalysisSession(initialState, {
    type: "stage",
    stage: "news",
    status: "running",
    message: "Calling realtime news search",
  })
  assert.equal(next.stages.news.status, "running")
})

test("heartbeat events are hidden by visible-event selectors", () => {
  // selector should filter them out
})

test("result event stores final CIO decision and marks connection completed", () => {
  // assert finalResult and completed connection state
})
```

- [ ] **Step 2: Run the reducer tests and verify they fail**

Run: `node --test --experimental-strip-types frontend/src/features/analysis-session/reducer.test.ts`
Expected: FAIL because the reducer and types do not exist yet.

- [ ] **Step 3: Implement the frontend session types, reducer, and selectors**

Implementation requirements:
- model the normalized event union explicitly
- store stage status/message separately from the raw event feed
- keep reducer pure and replayable
- add selectors that:
  - return stage-card props
  - hide heartbeat events
  - expose the final CIO markdown payload

- [ ] **Step 4: Re-run the reducer tests and verify they pass**

Run: `node --test --experimental-strip-types frontend/src/features/analysis-session/reducer.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/analysis-session/types.ts frontend/src/features/analysis-session/reducer.ts frontend/src/features/analysis-session/selectors.ts frontend/src/features/analysis-session/reducer.test.ts
git commit -m "feat(frontend): add analysis session reducer"
```

### Task 6: Rework the chat panel into a mixed progress UI without exposing sub-report bodies

**Files:**
- Create: `frontend/src/components/chat/AnalysisStageCards.tsx`
- Create: `frontend/src/components/chat/AnalysisEventFeed.tsx`
- Create: `frontend/src/components/chat/AnalysisFinalReport.tsx`
- Create: `frontend/src/components/chat/AnalysisProgress.test.ts`
- Modify: `frontend/src/components/chat/ChatPanel.tsx`
- Modify: `frontend/src/components/chat/ResultCard.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts`

- [ ] **Step 1: Write the failing frontend progress UI regression tests**

Use source-level checks plus reducer-driven assumptions:

```ts
test("chat progress UI uses Analysis Progress copy and stage cards", () => {
  assert.match(chatPanelSource, /Analysis Progress/)
  assert.match(chatPanelSource, /AnalysisStageCards/)
})

test("result card renders final CIO markdown but not quant/news/social tabs", () => {
  assert.doesNotMatch(resultCardSource, /Quant Analysis|News Sentiment|Social Sentiment/)
})
```

- [ ] **Step 2: Run the new frontend progress tests and verify they fail**

Run: `node --test --experimental-strip-types frontend/src/components/chat/AnalysisProgress.test.ts frontend/src/features/analysis-session/reducer.test.ts`
Expected: FAIL because the new components and copy do not exist yet.

- [ ] **Step 3: Implement the mixed progress UI and typed event consumption**

Implementation outline:

```tsx
<ResultCard ...>
  <AnalysisStageCards stages={stageCards} />
  <AnalysisEventFeed events={visibleEvents} />
  <AnalysisFinalReport markdown={finalDecision} />
</ResultCard>
```

Required behavior:
- keep `ChatPanel` as the session container
- switch `ChatPanel` from `useState<string[]>` progress tracking to the reducer
- use low-priority updates for event-feed append work
- keep the user input responsive while events stream
- show stage cards plus event feed during execution
- show only the final CIO markdown body when the run completes
- preserve current `EventSource` transport and cleanup semantics
- keep product copy in English and use `Analysis Progress`

- [ ] **Step 4: Run focused frontend tests and static verification**

Run: `node --test --experimental-strip-types frontend/src/features/analysis-session/reducer.test.ts frontend/src/components/chat/AnalysisProgress.test.ts frontend/src/components/chat/MarkdownRenderer.test.ts`
Expected: PASS

Run: `cd frontend && pnpm lint src/components/chat/ChatPanel.tsx src/components/chat/ResultCard.tsx src/components/chat/AnalysisStageCards.tsx src/components/chat/AnalysisEventFeed.tsx src/components/chat/AnalysisFinalReport.tsx src/features/analysis-session/types.ts src/features/analysis-session/reducer.ts src/features/analysis-session/selectors.ts src/lib/api.ts src/lib/types.ts`
Expected: PASS

Run: `cd frontend && pnpm type-check`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/AnalysisStageCards.tsx frontend/src/components/chat/AnalysisEventFeed.tsx frontend/src/components/chat/AnalysisFinalReport.tsx frontend/src/components/chat/AnalysisProgress.test.ts frontend/src/components/chat/ChatPanel.tsx frontend/src/components/chat/ResultCard.tsx frontend/src/lib/api.ts frontend/src/lib/types.ts
git commit -m "feat(frontend): show streamed analysis progress"
```

## Chunk 4: Feature-Level Verification

### Task 7: Run the focused cross-stack regression suite for the feature branch

**Files:**
- Test: `tests/test_agent_history.py`
- Test: `tests/test_analysis_runtime.py`
- Test: `tests/test_analysis_stage_events.py`
- Test: `tests/test_analyze_routes.py`
- Test: `frontend/src/features/analysis-session/reducer.test.ts`
- Test: `frontend/src/components/chat/AnalysisProgress.test.ts`
- Test: `frontend/src/components/chat/MarkdownRenderer.test.ts`

- [ ] **Step 1: Run the backend-focused regression suite**

Run: `uv run pytest tests/test_agent_history.py tests/test_analysis_runtime.py tests/test_analysis_stage_events.py tests/test_analyze_routes.py -q`
Expected: PASS

- [ ] **Step 2: Run the frontend Node tests for the new progress flow**

Run: `node --test --experimental-strip-types frontend/src/features/analysis-session/reducer.test.ts frontend/src/components/chat/AnalysisProgress.test.ts frontend/src/components/chat/MarkdownRenderer.test.ts`
Expected: PASS

- [ ] **Step 3: Run frontend lint and type checks**

Run: `cd frontend && pnpm lint src/components/chat/ChatPanel.tsx src/components/chat/ResultCard.tsx src/components/chat/AnalysisStageCards.tsx src/components/chat/AnalysisEventFeed.tsx src/components/chat/AnalysisFinalReport.tsx src/components/chat/AnalysisProgress.test.ts src/features/analysis-session/types.ts src/features/analysis-session/reducer.ts src/features/analysis-session/selectors.ts src/features/analysis-session/reducer.test.ts src/lib/api.ts src/lib/types.ts`
Expected: PASS

Run: `cd frontend && pnpm type-check`
Expected: PASS

- [ ] **Step 4: Review final feature diff for intended scope**

Run: `git diff -- app/analysis app/api/models app/api/routes/analyze.py app/graph_multi.py app/quant/generate_report.py app/news/generate_report.py app/social/generate_report.py app/database/agent_history.py tests/test_agent_history.py tests/test_analysis_runtime.py tests/test_analysis_stage_events.py tests/test_analyze_routes.py frontend/src/components/chat frontend/src/features/analysis-session frontend/src/lib/api.ts frontend/src/lib/types.ts docs/superpowers/specs/2026-04-08-analysis-progress-streaming-design.md docs/superpowers/plans/2026-04-08-analysis-progress-streaming.md`
Expected: Only analysis progress streaming files and their tests are changed.

Plan complete and saved to `docs/superpowers/plans/2026-04-08-analysis-progress-streaming.md`. Ready to execute?
