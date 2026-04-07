import type {
  Report,
  AnalyzeRequest,
  AnalyzeResponse,
  MCPStatus,
  HealthResponse,
  StockQuotesResponse,
  OHLCResponse,
  OHLCRecord,
  DataStatusResponse,
  CryptoQuotesResponse,
} from "./types";
import type {
  AnalysisEventStage,
  AnalysisEventStatus,
  AnalysisEventType,
  AnalysisReportMap,
  AnalysisStreamEvent,
  AnalysisStreamResult,
} from "@/features/analysis-session/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown,
  ) {
    super(message);
    this.name = "APIError";
  }
}

async function fetchAPI<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new APIError(
        errorData.message || `HTTP ${response.status}`,
        response.status,
        errorData,
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }
    throw new APIError(
      error instanceof Error ? error.message : "Network error",
      0,
    );
  }
}

const ANALYSIS_EVENT_STAGES = new Set<AnalysisEventStage>([
  "system",
  "quant",
  "news",
  "social",
  "cio",
]);

const ANALYSIS_EVENT_STATUSES = new Set<AnalysisEventStatus>([
  "pending",
  "running",
  "completed",
  "failed",
]);

const ANALYSIS_EVENT_TYPES = new Set<AnalysisEventType>([
  "stage",
  "tool_call",
  "tool_result",
  "result",
  "error",
  "heartbeat",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isAnalysisReportMap(value: unknown): value is AnalysisReportMap {
  if (!isRecord(value)) {
    return false;
  }

  return (
    (typeof value.cio === "string" || value.cio === null) &&
    (typeof value.quant === "string" || value.quant === null) &&
    (typeof value.news === "string" || value.news === null) &&
    (typeof value.social === "string" || value.social === null)
  );
}

function isAnalysisStreamResult(value: unknown): value is AnalysisStreamResult {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.report_id === "string" &&
    typeof value.status === "string" &&
    typeof value.final_decision === "string" &&
    isRecord(value.quant_analysis) &&
    isRecord(value.news_sentiment) &&
    isRecord(value.social_sentiment) &&
    isAnalysisReportMap(value.reports)
  );
}

function parseAnalysisEventType(value: unknown): AnalysisEventType | null {
  return typeof value === "string" &&
    ANALYSIS_EVENT_TYPES.has(value as AnalysisEventType)
    ? (value as AnalysisEventType)
    : null;
}

function parseAnalysisEventStage(value: unknown): AnalysisEventStage {
  return typeof value === "string" &&
    ANALYSIS_EVENT_STAGES.has(value as AnalysisEventStage)
    ? (value as AnalysisEventStage)
    : "system";
}

function parseAnalysisEventStatus(value: unknown): AnalysisEventStatus {
  return typeof value === "string" &&
    ANALYSIS_EVENT_STATUSES.has(value as AnalysisEventStatus)
    ? (value as AnalysisEventStatus)
    : "running";
}

export const api = {
  // Health check
  health: () => fetchAPI<HealthResponse>("/api/health"),

  // MCP status
  mcpStatus: () => fetchAPI<MCPStatus>("/api/mcp/status"),

  // Get all reports
  getReports: () =>
    fetchAPI<Report[]>("/api/reports", {
      cache: "no-store",
    }),

  // Get single report
  getReport: (id: string) => fetchAPI<Report>(`/api/reports/${id}`),

  // Start analysis (returns immediately, use SSE for progress)
  analyze: (request: AnalyzeRequest) =>
    fetchAPI<AnalyzeResponse>("/api/analyze", {
      method: "POST",
      body: JSON.stringify(request),
    }),

  // Create EventSource for SSE
  createAnalyzeStream: (query: string) => {
    const params = new URLSearchParams({ query });
    return new EventSource(`${API_BASE_URL}/api/analyze/stream?${params}`);
  },

  parseAnalysisStreamEvent: (payload: string): AnalysisStreamEvent | null => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(payload);
    } catch {
      return null;
    }

    if (!isRecord(parsed)) {
      return null;
    }

    const type = parseAnalysisEventType(parsed.type);
    if (!type) {
      return null;
    }

    const baseEvent = {
      event_id:
        typeof parsed.event_id === "string" ? parsed.event_id : undefined,
      sequence:
        typeof parsed.sequence === "number" ? parsed.sequence : undefined,
      run_id: typeof parsed.run_id === "string" ? parsed.run_id : undefined,
      timestamp:
        typeof parsed.timestamp === "string" ? parsed.timestamp : undefined,
      type,
      stage: parseAnalysisEventStage(parsed.stage),
      status: parseAnalysisEventStatus(parsed.status),
      message: typeof parsed.message === "string" ? parsed.message : "",
    };

    if (type === "result") {
      const resultData = isAnalysisStreamResult(parsed.data)
        ? parsed.data
        : {
            report_id: baseEvent.run_id ?? "unknown_run",
            status: "completed",
            final_decision: "",
            quant_analysis: {},
            news_sentiment: {},
            social_sentiment: {},
            reports: {
              cio: null,
              quant: null,
              news: null,
              social: null,
            },
          };

      return {
        ...baseEvent,
        type,
        data: resultData,
      };
    }

    return {
      ...baseEvent,
      type,
      data: isRecord(parsed.data) ? parsed.data : {},
    };
  },

  // Get stock quotes for given symbols
  getStockQuotes: (symbols: string[]) =>
    fetchAPI<StockQuotesResponse>(
      `/api/stocks/quotes?symbols=${symbols.join(",")}`,
    ),

  // Get OHLC data for a stock
  getStockOHLC: (
    symbol: string,
    start?: string,
    end?: string,
    interval: string = "day",
  ) => {
    const params = new URLSearchParams();
    if (start) params.append("start", start);
    if (end) params.append("end", end);
    params.append("interval", interval);
    const query = params.toString();
    return fetchAPI<OHLCResponse>(
      `/api/stocks/${symbol}/ohlc${query ? `?${query}` : ""}`,
    );
  },

  // Get data status for a stock
  getDataStatus: (symbol: string) =>
    fetchAPI<DataStatusResponse>(`/api/stocks/${symbol}/data-status`),

  // Get crypto quotes
  getCryptoQuotes: (symbols: string[]) =>
    fetchAPI<CryptoQuotesResponse>(
      `/api/crypto/quotes?symbols=${symbols.join(",")}`,
    ),

  // Get OHLC data for a crypto symbol
  getCryptoOHLC: (
    symbol: string,
    start?: string,
    end?: string,
    interval: string = "15m",
  ) => {
    // Convert symbol format: BTC-USDT -> BTCUSDT for klines endpoint
    const binanceSymbol = symbol.replace("-", "");
    const params = new URLSearchParams();
    params.append("symbol", binanceSymbol);
    params.append("interval", interval);
    if (start) params.append("start", start);
    if (end) params.append("end", end);
    const query = params.toString();

    // Use klines endpoint which merges hot cache and cold database
    return fetchAPI<OHLCRecord[]>(`/api/crypto/klines?${query}`).then(
      (data) => {
        // Transform klines response to OHLC format
        return {
          symbol: symbol,
          data: data.map((item) => ({
            date: item.date,
            open: item.open,
            high: item.high,
            low: item.low,
            close: item.close,
            volume: item.volume,
          })),
        };
      },
    );
  },
};

export { APIError };
