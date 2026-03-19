import type {
  Report,
  AnalyzeRequest,
  AnalyzeResponse,
  MCPStatus,
  HealthResponse,
  SettingsResponse,
  SettingsRequest,
  StockQuotesResponse,
} from './types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'APIError';
  }
}

async function fetchAPI<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new APIError(
        errorData.message || `HTTP ${response.status}`,
        response.status,
        errorData
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }
    throw new APIError(
      error instanceof Error ? error.message : 'Network error',
      0
    );
  }
}

export const api = {
  // Health check
  health: () => fetchAPI<HealthResponse>('/api/health'),

  // MCP status
  mcpStatus: () => fetchAPI<MCPStatus>('/api/mcp/status'),

  // Get all reports
  getReports: () => fetchAPI<Report[]>('/api/reports'),

  // Get single report
  getReport: (id: string) => fetchAPI<Report>(`/api/reports/${id}`),

  // Start analysis (returns immediately, use SSE for progress)
  analyze: (request: AnalyzeRequest) =>
    fetchAPI<AnalyzeResponse>('/api/analyze', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  // Create EventSource for SSE
  createAnalyzeStream: (query: string) => {
    const params = new URLSearchParams({ query });
    return new EventSource(`${API_BASE_URL}/api/analyze/stream?${params}`);
  },

  // Settings
  getSettings: () => fetchAPI<SettingsResponse>('/api/settings'),

  updateSettings: (data: SettingsRequest) =>
    fetchAPI<SettingsResponse>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Get stock quotes for given symbols
  getStockQuotes: (symbols: string[]) =>
    fetchAPI<StockQuotesResponse>(
      `/api/stocks/quotes?symbols=${symbols.join(',')}`
    ),
};

export { APIError };
