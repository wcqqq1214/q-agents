import type {
  Report,
  AnalyzeRequest,
  AnalyzeResponse,
  MCPStatus,
  HealthResponse,
  SettingsResponse,
  SettingsRequest,
  StockQuotesResponse,
  OHLCResponse,
  OHLCRecord,
  DataStatusResponse,
  CryptoQuotesResponse,
} from "./types";

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

  // Settings
  getSettings: () => fetchAPI<SettingsResponse>("/api/settings"),

  updateSettings: (data: SettingsRequest) =>
    fetchAPI<SettingsResponse>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

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
