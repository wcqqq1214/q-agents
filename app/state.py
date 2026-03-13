"""Shared state definitions for the multi-agent finance graph."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class AgentState(TypedDict):
    """Global state for the Fan-out / Fan-in multi-agent graph.

    Attributes:
        query: User's original question (e.g. analysis request for BTC-USD or NVDA).
        quant_report: Technical/quantitative report produced by Quant_Agent only.
        news_report: News-sentiment report produced by News_Agent only.
        social_report: Retail/social sentiment report produced by Social_Agent only.
        final_decision: Synthesized report from CIO_Agent (no tools).
    """

    query: str
    quant_report: NotRequired[str]
    news_report: NotRequired[str]
    social_report: NotRequired[str]
    final_decision: NotRequired[str]
