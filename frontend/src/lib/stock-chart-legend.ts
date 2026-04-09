import type { OHLCRecord, StockInfo } from "./types";

type ChartTime =
  | number
  | string
  | { year: number; month: number; day: number }
  | null
  | undefined;

interface ResolveLegendChangeMetricsParams {
  assetType: "crypto" | "stocks";
  hoveredTime: ChartTime;
  latestTime: ChartTime;
  latestDateString?: string | null;
  ohlc: Pick<OHLCRecord, "open" | "close">;
  previousClose?: number | null;
  liveQuote?: StockInfo | null;
  currentUsMarketDate: string;
}

export interface LegendChangeMetrics {
  label: string | null;
  percent: number;
  isUp: boolean;
}

function isBusinessDay(
  time: ChartTime,
): time is { year: number; month: number; day: number } {
  return (
    typeof time === "object" &&
    time !== null &&
    "year" in time &&
    "month" in time &&
    "day" in time
  );
}

function areTimesEqual(left: ChartTime, right: ChartTime): boolean {
  if (left === right) {
    return true;
  }
  if (isBusinessDay(left) && isBusinessDay(right)) {
    return (
      left.year === right.year &&
      left.month === right.month &&
      left.day === right.day
    );
  }
  return false;
}

export function resolveLegendChangeMetrics({
  assetType,
  hoveredTime,
  latestTime,
  latestDateString,
  ohlc,
  previousClose,
  liveQuote,
  currentUsMarketDate,
}: ResolveLegendChangeMetricsParams): LegendChangeMetrics {
  const candleChange = ohlc.close - ohlc.open;
  const candlePercent = ohlc.open === 0 ? 0 : (candleChange / ohlc.open) * 100;
  const fallbackMetrics: LegendChangeMetrics = {
    label: null,
    percent: candlePercent,
    isUp: candleChange >= 0,
  };
  const previousCloseMetrics =
    previousClose == null || previousClose === 0
      ? null
      : {
          label: null,
          percent: ((ohlc.close - previousClose) / previousClose) * 100,
          isUp: ohlc.close >= previousClose,
        };

  const resolvedLatestDateString =
    latestDateString ??
    (typeof latestTime === "string"
      ? latestTime.split("T")[0]
      : isBusinessDay(latestTime)
        ? `${latestTime.year}-${String(latestTime.month).padStart(2, "0")}-${String(latestTime.day).padStart(2, "0")}`
        : null);

  if (
    assetType !== "stocks" ||
    !areTimesEqual(hoveredTime, latestTime) ||
    resolvedLatestDateString !== currentUsMarketDate ||
    liveQuote?.changePercent == null
  ) {
    return previousCloseMetrics ?? fallbackMetrics;
  }

  const quoteDirection = liveQuote.change ?? liveQuote.changePercent;
  return {
    label: null,
    percent: liveQuote.changePercent,
    isUp: quoteDirection >= 0,
  };
}
