import {
  ANALYSIS_STAGE_KEYS,
  type AnalysisEventStatus,
  type AnalysisSessionAction,
  type AnalysisSessionState,
  type AnalysisStageKey,
  type AnalysisStreamEvent,
} from "./types.ts";

function createInitialStages() {
  return ANALYSIS_STAGE_KEYS.reduce<
    Record<
      AnalysisStageKey,
      { status: AnalysisEventStatus; message: string | null }
    >
  >(
    (stages, key) => {
      stages[key] = { status: "pending", message: null };
      return stages;
    },
    {
      quant: { status: "pending", message: null },
      news: { status: "pending", message: null },
      social: { status: "pending", message: null },
      cio: { status: "pending", message: null },
    },
  );
}

function isStageKey(
  stage: AnalysisStreamEvent["stage"],
): stage is AnalysisStageKey {
  return ANALYSIS_STAGE_KEYS.includes(stage as AnalysisStageKey);
}

function reduceStageState(
  state: AnalysisSessionState,
  event: AnalysisStreamEvent,
) {
  if (!isStageKey(event.stage) || event.type === "heartbeat") {
    return state.stages;
  }

  const currentStage = state.stages[event.stage];
  let nextStage = currentStage;

  if (event.type === "stage") {
    nextStage = { status: event.status, message: event.message };
  } else if (event.type === "tool_call") {
    nextStage = {
      status:
        currentStage.status === "pending" ? "running" : currentStage.status,
      message: event.message,
    };
  } else if (event.type === "tool_result") {
    nextStage = {
      status:
        currentStage.status === "pending" ? "running" : currentStage.status,
      message: event.message,
    };
  } else if (event.type === "result") {
    nextStage = { status: "completed", message: event.message };
  } else if (event.type === "error") {
    nextStage = { status: "failed", message: event.message };
  }

  if (
    nextStage.status === currentStage.status &&
    nextStage.message === currentStage.message
  ) {
    return state.stages;
  }

  return {
    ...state.stages,
    [event.stage]: nextStage,
  };
}

export function createInitialAnalysisSessionState(): AnalysisSessionState {
  return {
    runId: null,
    connection: "idle",
    stages: createInitialStages(),
    events: [],
    finalResult: null,
    error: null,
  };
}

export function reduceAnalysisSession(
  state: AnalysisSessionState,
  action: AnalysisSessionAction,
): AnalysisSessionState {
  if (action.type === "reset") {
    return createInitialAnalysisSessionState();
  }

  if (action.type === "session_started") {
    return {
      ...createInitialAnalysisSessionState(),
      connection: "connecting",
    };
  }

  if (action.type === "connection_error") {
    return {
      ...state,
      connection: "failed",
      error: action.message,
    };
  }

  const { event } = action;
  const stages = reduceStageState(state, event);

  return {
    runId:
      event.run_id ??
      (event.type === "result" ? event.data.report_id : state.runId),
    connection:
      event.type === "result"
        ? "completed"
        : event.type === "error"
          ? "failed"
          : "streaming",
    stages,
    events: [...state.events, event],
    finalResult: event.type === "result" ? event.data : state.finalResult,
    error: event.type === "error" ? event.message : state.error,
  };
}
