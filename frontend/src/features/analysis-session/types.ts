export const ANALYSIS_STAGE_KEYS = ["quant", "news", "social", "cio"] as const;

export const ANALYSIS_STAGE_LABELS = {
  quant: "Quant",
  news: "News",
  social: "Social",
  cio: "CIO",
} as const;

export type AnalysisStageKey = (typeof ANALYSIS_STAGE_KEYS)[number];
export type AnalysisEventStage = AnalysisStageKey | "system";
export type AnalysisConnectionState =
  | "idle"
  | "connecting"
  | "streaming"
  | "completed"
  | "failed";
export type AnalysisEventType =
  | "stage"
  | "tool_call"
  | "tool_result"
  | "result"
  | "error"
  | "heartbeat";
export type AnalysisEventStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface AnalysisStageState {
  status: AnalysisEventStatus;
  message: string | null;
}

export interface AnalysisReportMap {
  cio: string | null;
  quant: string | null;
  news: string | null;
  social: string | null;
}

export interface AnalysisStreamResult {
  report_id: string;
  status: string;
  final_decision: string;
  quant_analysis: Record<string, unknown>;
  news_sentiment: Record<string, unknown>;
  social_sentiment: Record<string, unknown>;
  reports: AnalysisReportMap;
}

export interface AnalysisEventBase {
  event_id?: string;
  sequence?: number;
  run_id?: string;
  timestamp?: string;
  stage: AnalysisEventStage;
  status: AnalysisEventStatus;
  message: string;
}

export interface AnalysisStageEvent extends AnalysisEventBase {
  type: "stage";
  data?: Record<string, unknown>;
}

export interface AnalysisToolCallEvent extends AnalysisEventBase {
  type: "tool_call";
  data?: Record<string, unknown>;
}

export interface AnalysisToolResultEvent extends AnalysisEventBase {
  type: "tool_result";
  data?: Record<string, unknown>;
}

export interface AnalysisResultEvent extends AnalysisEventBase {
  type: "result";
  data: AnalysisStreamResult;
}

export interface AnalysisErrorEvent extends AnalysisEventBase {
  type: "error";
  data?: Record<string, unknown>;
}

export interface AnalysisHeartbeatEvent extends AnalysisEventBase {
  type: "heartbeat";
  data?: Record<string, unknown>;
}

export type AnalysisStreamEvent =
  | AnalysisStageEvent
  | AnalysisToolCallEvent
  | AnalysisToolResultEvent
  | AnalysisResultEvent
  | AnalysisErrorEvent
  | AnalysisHeartbeatEvent;

export interface AnalysisSessionState {
  runId: string | null;
  connection: AnalysisConnectionState;
  stages: Record<AnalysisStageKey, AnalysisStageState>;
  events: AnalysisStreamEvent[];
  finalResult: AnalysisStreamResult | null;
  error: string | null;
}

export type AnalysisSessionAction =
  | { type: "reset" }
  | { type: "session_started" }
  | { type: "stream_event"; event: AnalysisStreamEvent }
  | { type: "connection_error"; message: string };

export interface AnalysisStageCard {
  key: AnalysisStageKey;
  label: (typeof ANALYSIS_STAGE_LABELS)[AnalysisStageKey];
  status: AnalysisEventStatus;
  message: string | null;
}
