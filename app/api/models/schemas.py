from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    query: str = Field(..., description="Stock symbol or query to analyze")


class AnalyzeResponse(BaseModel):
    report_id: str
    status: str


class ReportTexts(BaseModel):
    cio: Optional[str] = None
    quant: Optional[str] = None
    news: Optional[str] = None
    social: Optional[str] = None


class Report(BaseModel):
    id: str
    symbol: str
    timestamp: str
    query: Optional[str] = None
    final_decision: Optional[str] = None
    quant_analysis: Optional[Dict[str, Any]] = None
    news_sentiment: Optional[Dict[str, Any]] = None
    social_sentiment: Optional[Dict[str, Any]] = None
    reports: Optional[ReportTexts] = None


class ServiceStatus(BaseModel):
    available: bool
    url: str
    error: Optional[str] = None
    managed: bool = False
    pid: Optional[int] = None
    tool_count: int = 0
    restart_count: int = 0


class MCPStatus(BaseModel):
    market_data: Optional[ServiceStatus] = None
    news_search: Optional[ServiceStatus] = None
    servers: Dict[str, ServiceStatus] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    timestamp: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class SettingsResponse(BaseModel):
    claude_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    polygon_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None


class SettingsRequest(BaseModel):
    claude_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    polygon_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None


class StockQuote(BaseModel):
    symbol: str
    name: str
    price: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = Field(None, alias="changePercent")
    logo: Optional[str] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None

    class Config:
        populate_by_name = True
        by_alias = True


class StockQuotesResponse(BaseModel):
    quotes: List[StockQuote]


# OKX-related models


class OKXOrderRequest(BaseModel):
    """OKX order request."""

    inst_id: str
    side: str  # buy/sell
    order_type: str  # market/limit/post_only/fok/ioc
    size: str
    price: Optional[str] = None
    client_order_id: Optional[str] = None
    reduce_only: Optional[bool] = False


class OKXBalance(BaseModel):
    """OKX account balance."""

    currency: str
    available: str
    frozen: str
    total: str


class OKXPosition(BaseModel):
    """OKX position details."""

    inst_id: str
    position_side: str  # long/short/net
    position: str
    available_position: str
    average_price: str
    unrealized_pnl: str
    leverage: str


class OKXOrderResponse(BaseModel):
    """OKX order response."""

    order_id: str
    client_order_id: str
    inst_id: str
    status: str  # live/partially_filled/filled/canceled
    side: str
    order_type: str
    size: str
    filled_size: str
    price: Optional[str]
    average_price: Optional[str]
    timestamp: str


class OKXTicker(BaseModel):
    """OKX ticker data."""

    inst_id: str
    last: str
    bid: str
    ask: str
    volume_24h: str
    high_24h: str
    low_24h: str
    timestamp: str
