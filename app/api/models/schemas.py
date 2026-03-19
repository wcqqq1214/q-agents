from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class AnalyzeRequest(BaseModel):
    query: str = Field(..., description="Stock symbol or query to analyze")


class AnalyzeResponse(BaseModel):
    report_id: str
    status: str


class Report(BaseModel):
    id: str
    symbol: str
    timestamp: str
    quant_analysis: Optional[Dict[str, Any]] = None
    news_sentiment: Optional[Dict[str, Any]] = None
    social_sentiment: Optional[Dict[str, Any]] = None


class ServiceStatus(BaseModel):
    available: bool
    url: str
    error: Optional[str] = None


class MCPStatus(BaseModel):
    market_data: ServiceStatus
    news_search: ServiceStatus


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
    change_percent: Optional[float] = None
    logo: Optional[str] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None


class StockQuotesResponse(BaseModel):
    quotes: List[StockQuote]
