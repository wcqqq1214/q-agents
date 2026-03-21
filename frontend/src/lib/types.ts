// API Response Types

export interface Report {
  id: string;
  symbol: string;
  timestamp: string;
  quant_analysis?: QuantAnalysis;
  news_sentiment?: NewsSentiment;
  social_sentiment?: SocialSentiment;
}

export interface QuantAnalysis {
  symbol: string;
  current_price: number;
  recommendation: string;
  confidence: number;
  technical_indicators?: Record<string, unknown>;
}

export interface NewsSentiment {
  symbol: string;
  overall_sentiment: string;
  sentiment_score: number;
  articles_analyzed: number;
  key_themes?: string[];
}

export interface SocialSentiment {
  symbol: string;
  overall_sentiment: string;
  sentiment_score: number;
  posts_analyzed: number;
  trending_topics?: string[];
}

export interface AnalyzeRequest {
  query: string;
}

export interface AnalyzeResponse {
  report_id: string;
  status: string;
}

export interface SSEEvent {
  type: 'progress' | 'result' | 'error';
  message?: string;
  step?: string;
  done?: boolean;
  data?: unknown;
}

export interface MCPStatus {
  market_data: ServiceStatus;
  news_search: ServiceStatus;
}

export interface ServiceStatus {
  available: boolean;
  url: string;
  error?: string;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
}

export interface SettingsResponse {
  claude_api_key?: string;
  openai_api_key?: string;
  polygon_api_key?: string;
  tavily_api_key?: string;
}

export interface SettingsRequest {
  claude_api_key?: string;
  openai_api_key?: string;
  polygon_api_key?: string;
  tavily_api_key?: string;
}

export interface StockInfo {
  symbol: string;
  name: string;
  logo?: string;
  price?: number;
  change?: number;
  changePercent?: number;
  timestamp?: string;
  error?: string;
}

export interface StockQuotesResponse {
  quotes: StockInfo[];
}

// OHLC Data Types
export interface OHLCRecord {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;  // Can be float from database
}

export interface OHLCResponse {
  symbol: string;
  data: OHLCRecord[];
}

export interface DataStatusResponse {
  symbol: string;
  last_update: string | null;
  data_start: string | null;
  data_end: string | null;
  total_records: number;
}

export type TimeRange = 'D' | 'W' | 'M' | 'Y' | '15M' | '1H' | '4H' | '1D' | '1W' | '1M' | '1Y';

// Crypto Types
export interface CryptoQuote {
  symbol: string;
  name: string;
  price: number;
  change: number;  // Price change amount (e.g., $261.09)
  changePercent: number;  // Price change percentage (e.g., 0.37%)
  volume24h: number;
  high24h: number;
  low24h: number;
}

export interface CryptoQuotesResponse {
  quotes: CryptoQuote[];
}
