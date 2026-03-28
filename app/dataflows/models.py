from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_serializer, model_validator


class StockCandle(BaseModel):
    """标准化的 OHLCV 数据"""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info):
        return dt.isoformat()

    @model_validator(mode="after")
    def validate_ohlc(self) -> "StockCandle":
        """验证 OHLC 数据逻辑一致性"""
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be <= open and close")
        if self.volume < 0:
            raise ValueError("volume must be >= 0")
        return self


class TechnicalIndicator(BaseModel):
    """技术指标数据"""

    timestamp: datetime
    indicator_name: str  # "SMA_20", "MACD", "RSI_14"
    value: float
    metadata: Optional[dict] = None

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info):
        return dt.isoformat()


class NewsArticle(BaseModel):
    """新闻文章"""

    title: str
    url: str
    published_at: datetime
    source: str
    summary: Optional[str] = None
    sentiment: Optional[float] = Field(None, ge=-1.0, le=1.0)

    @field_serializer("published_at")
    def serialize_published_at(self, dt: datetime, _info):
        return dt.isoformat()


class FundamentalsData(BaseModel):
    """基本面数据"""

    symbol: str
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    revenue: Optional[float] = None
    profit_margin: Optional[float] = None
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_updated_at(self, dt: datetime, _info):
        return dt.isoformat()
