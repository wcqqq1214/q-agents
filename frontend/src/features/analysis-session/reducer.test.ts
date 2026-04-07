import assert from "node:assert/strict";
import test from "node:test";

function makeEvent(overrides: Record<string, unknown> = {}) {
  return {
    event_id: "evt_0001",
    sequence: 1,
    run_id: "run_0001",
    timestamp: "2026-04-08T12:00:00Z",
    type: "stage",
    stage: "system",
    status: "running",
    message: "Analysis started",
    data: {},
    ...overrides,
  };
}

async function loadReducerModule() {
  const reducerUrl = new URL("./reducer.ts", import.meta.url).href;
  const selectorsUrl = new URL("./selectors.ts", import.meta.url).href;
  const reducerModule = await import(reducerUrl);
  const selectorsModule = await import(selectorsUrl);
  return { ...reducerModule, ...selectorsModule };
}

test("stage event moves a stage from pending to running", async () => {
  const { createInitialAnalysisSessionState, reduceAnalysisSession } =
    await loadReducerModule();

  const next = reduceAnalysisSession(createInitialAnalysisSessionState(), {
    type: "stream_event",
    event: makeEvent({
      type: "stage",
      stage: "news",
      status: "running",
      message: "Calling realtime news search",
    }),
  });

  assert.equal(next.connection, "streaming");
  assert.equal(next.stages.news.status, "running");
  assert.equal(next.stages.news.message, "Calling realtime news search");
});

test("heartbeat events are hidden by visible-event selectors", async () => {
  const {
    createInitialAnalysisSessionState,
    reduceAnalysisSession,
    selectVisibleAnalysisEvents,
  } = await loadReducerModule();

  const withHeartbeat = reduceAnalysisSession(
    createInitialAnalysisSessionState(),
    {
      type: "stream_event",
      event: makeEvent({
        type: "heartbeat",
        stage: "system",
        status: "running",
        message: "Analysis still running",
      }),
    },
  );
  const withToolCall = reduceAnalysisSession(withHeartbeat, {
    type: "stream_event",
    event: makeEvent({
      event_id: "evt_0002",
      sequence: 2,
      type: "tool_call",
      stage: "quant",
      status: "running",
      message: "Running ML quant analysis",
      data: { tool: "run_ml_quant_analysis" },
    }),
  });

  assert.equal(withToolCall.events.length, 2);
  assert.deepEqual(
    selectVisibleAnalysisEvents(withToolCall).map(
      (event: { type: string }) => event.type,
    ),
    ["tool_call"],
  );
});

test("result event stores final CIO decision and marks connection completed", async () => {
  const {
    createInitialAnalysisSessionState,
    reduceAnalysisSession,
    selectAnalysisStageCards,
    selectFinalCioMarkdown,
  } = await loadReducerModule();

  const next = reduceAnalysisSession(createInitialAnalysisSessionState(), {
    type: "stream_event",
    event: makeEvent({
      type: "result",
      stage: "cio",
      status: "completed",
      message: "Analysis completed",
      data: {
        report_id: "20260408_120000_NVDA",
        status: "completed",
        final_decision: "# CIO Decision\n\nStay constructive on NVDA.",
        quant_analysis: {},
        news_sentiment: {},
        social_sentiment: {},
        reports: {
          cio: "# CIO Decision\n\nStay constructive on NVDA.",
          quant: "# Quantitative Technical Report",
          news: "# Macro News Sentiment Report",
          social: "# Social Retail Sentiment Report",
        },
      },
    }),
  });

  assert.equal(next.connection, "completed");
  assert.equal(
    next.finalResult?.final_decision,
    "# CIO Decision\n\nStay constructive on NVDA.",
  );
  assert.equal(
    selectFinalCioMarkdown(next),
    "# CIO Decision\n\nStay constructive on NVDA.",
  );
  assert.equal(selectAnalysisStageCards(next).at(-1)?.status, "completed");
});

test("error event marks the failing stage and stores the terminal message", async () => {
  const { createInitialAnalysisSessionState, reduceAnalysisSession } =
    await loadReducerModule();

  const next = reduceAnalysisSession(createInitialAnalysisSessionState(), {
    type: "stream_event",
    event: makeEvent({
      type: "error",
      stage: "social",
      status: "failed",
      message: "Reddit ingestion failed",
    }),
  });

  assert.equal(next.connection, "failed");
  assert.equal(next.error, "Reddit ingestion failed");
  assert.equal(next.stages.social.status, "failed");
  assert.equal(next.stages.social.message, "Reddit ingestion failed");
});
