import {
  ANALYSIS_STAGE_KEYS,
  ANALYSIS_STAGE_LABELS,
  type AnalysisSessionState,
  type AnalysisStageCard,
} from "./types.ts";

export function selectAnalysisStageCards(
  state: AnalysisSessionState,
): AnalysisStageCard[] {
  return ANALYSIS_STAGE_KEYS.map((key) => ({
    key,
    label: ANALYSIS_STAGE_LABELS[key],
    status: state.stages[key].status,
    message: state.stages[key].message,
  }));
}

export function selectVisibleAnalysisEvents(state: AnalysisSessionState) {
  return state.events.filter((event) => event.type !== "heartbeat");
}

export function selectFinalCioMarkdown(
  state: AnalysisSessionState,
): string | null {
  return (
    state.finalResult?.final_decision || state.finalResult?.reports.cio || null
  );
}
