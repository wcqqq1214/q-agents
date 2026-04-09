import assert from "node:assert/strict";
import test from "node:test";

import type { OHLCRecord, StockInfo } from "./types";

const FIXED_MARKET_NOW = new Date("2026-04-09T11:37:00-04:00");
const PREVIOUS_TRADING_DATE = "2026-04-08";

async function loadModule() {
  const moduleUrl = new URL("./stock-chart-legend.ts", import.meta.url).href;
  return import(moduleUrl);
}

function getCurrentUsMarketDateString(now: Date): string {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(now);
}

const CURRENT_MARKET_DATE = getCurrentUsMarketDateString(FIXED_MARKET_NOW);

const previousBar: OHLCRecord = {
  date: PREVIOUS_TRADING_DATE,
  open: 606.0,
  high: 629.95,
  low: 591.83,
  close: 612.42,
  volume: 31_859_600,
};
const PREVIOUS_BAR_CLOSE = 575.05;

const latestBar: OHLCRecord = {
  date: CURRENT_MARKET_DATE,
  open: 626.97,
  high: 632.7,
  low: 623.0,
  close: 630.49,
  volume: 22_377_485,
};

const liveQuote: StockInfo = {
  symbol: "META",
  name: "Meta Platforms Inc.",
  price: 620.425,
  change: 45.375,
  changePercent: 7.89,
};

test("latest stock market-day legend uses live quote day change percent for the newest bar", async () => {
  const { resolveLegendChangeMetrics } = await loadModule();

  const metrics = resolveLegendChangeMetrics({
    assetType: "stocks",
    hoveredTime: CURRENT_MARKET_DATE,
    latestTime: CURRENT_MARKET_DATE,
    latestDateString: CURRENT_MARKET_DATE,
    ohlc: latestBar,
    previousClose: previousBar.close,
    liveQuote,
    currentUsMarketDate: CURRENT_MARKET_DATE,
  });

  assert.deepEqual(metrics, {
    label: null,
    percent: 7.89,
    isUp: true,
  });
});

test("historical stock bars use current close versus previous close percentage", async () => {
  const { resolveLegendChangeMetrics } = await loadModule();

  const metrics = resolveLegendChangeMetrics({
    assetType: "stocks",
    hoveredTime: PREVIOUS_TRADING_DATE,
    latestTime: CURRENT_MARKET_DATE,
    latestDateString: CURRENT_MARKET_DATE,
    ohlc: previousBar,
    previousClose: PREVIOUS_BAR_CLOSE,
    liveQuote,
    currentUsMarketDate: CURRENT_MARKET_DATE,
  });

  assert.deepEqual(metrics, {
    label: null,
    percent:
      ((previousBar.close - PREVIOUS_BAR_CLOSE) / PREVIOUS_BAR_CLOSE) * 100,
    isUp: true,
  });
});

test("latest stock legend falls back to candle metrics when quote day change percent is null", async () => {
  const { resolveLegendChangeMetrics } = await loadModule();

  const metrics = resolveLegendChangeMetrics({
    assetType: "stocks",
    hoveredTime: CURRENT_MARKET_DATE,
    latestTime: CURRENT_MARKET_DATE,
    latestDateString: CURRENT_MARKET_DATE,
    ohlc: latestBar,
    previousClose: previousBar.close,
    liveQuote: {
      ...liveQuote,
      changePercent: null as unknown as number,
    },
    currentUsMarketDate: CURRENT_MARKET_DATE,
  });

  assert.deepEqual(metrics, {
    label: null,
    percent: ((latestBar.close - previousBar.close) / previousBar.close) * 100,
    isUp: true,
  });
});

test("previous trading day bar stays on candle percentage even when it is yesterday in local time", async () => {
  const { resolveLegendChangeMetrics } = await loadModule();

  const metrics = resolveLegendChangeMetrics({
    assetType: "stocks",
    hoveredTime: PREVIOUS_TRADING_DATE,
    latestTime: PREVIOUS_TRADING_DATE,
    latestDateString: PREVIOUS_TRADING_DATE,
    ohlc: previousBar,
    previousClose: PREVIOUS_BAR_CLOSE,
    liveQuote,
    currentUsMarketDate: CURRENT_MARKET_DATE,
  });

  assert.deepEqual(metrics, {
    label: null,
    percent:
      ((previousBar.close - PREVIOUS_BAR_CLOSE) / PREVIOUS_BAR_CLOSE) * 100,
    isUp: true,
  });
});

test("latest stock bar can use live quote when chart times are numeric", async () => {
  const { resolveLegendChangeMetrics } = await loadModule();

  const metrics = resolveLegendChangeMetrics({
    assetType: "stocks",
    hoveredTime: 1_744_202_400,
    latestTime: 1_744_202_400,
    latestDateString: CURRENT_MARKET_DATE,
    ohlc: latestBar,
    previousClose: previousBar.close,
    liveQuote,
    currentUsMarketDate: CURRENT_MARKET_DATE,
  });

  assert.deepEqual(metrics, {
    label: null,
    percent: 7.89,
    isUp: true,
  });
});
