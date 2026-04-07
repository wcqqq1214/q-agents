import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const chatPanelSource = readFileSync(
  new URL("./ChatPanel.tsx", import.meta.url),
  "utf8",
);
const resultCardSource = readFileSync(
  new URL("./ResultCard.tsx", import.meta.url),
  "utf8",
);
const stageCardsSource = readFileSync(
  new URL("./AnalysisStageCards.tsx", import.meta.url),
  "utf8",
);
const eventFeedSource = readFileSync(
  new URL("./AnalysisEventFeed.tsx", import.meta.url),
  "utf8",
);
const finalReportSource = readFileSync(
  new URL("./AnalysisFinalReport.tsx", import.meta.url),
  "utf8",
);

test("chat progress UI uses Analysis Progress copy and stage cards", () => {
  assert.match(chatPanelSource, /Analysis Progress/);
  assert.match(chatPanelSource, /selectAnalysisStageCards/);
  assert.match(chatPanelSource, /stages=\{stageCards\}/);
  assert.match(chatPanelSource, /useTransition/);
  assert.doesNotMatch(chatPanelSource, /setProgress/);
  assert.doesNotMatch(chatPanelSource, /type SSEEvent/);
});

test("result card composes the mixed progress subcomponents", () => {
  assert.match(resultCardSource, /AnalysisStageCards/);
  assert.match(resultCardSource, /AnalysisEventFeed/);
  assert.match(resultCardSource, /AnalysisFinalReport/);
  assert.doesNotMatch(resultCardSource, /progress:\s*string\[\]/);
  assert.doesNotMatch(resultCardSource, /Quant Analysis/);
  assert.doesNotMatch(resultCardSource, /News Sentiment/);
  assert.doesNotMatch(resultCardSource, /Social Sentiment/);
});

test("analysis progress subcomponents keep the expected structure", () => {
  assert.match(stageCardsSource, /Quant/);
  assert.match(stageCardsSource, /News/);
  assert.match(stageCardsSource, /Social/);
  assert.match(stageCardsSource, /CIO/);

  assert.match(eventFeedSource, /Analysis Event Feed/);
  assert.match(eventFeedSource, /autoScroll/);
  assert.match(finalReportSource, /MarkdownRenderer/);
  assert.match(finalReportSource, /Final CIO Report/);
});
