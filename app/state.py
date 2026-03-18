"""Shared state definitions for the multi-agent finance graph."""

from __future__ import annotations

from typing import Any, Dict, NotRequired, TypedDict


class AgentState(TypedDict):
    """Global state for the Fan-out / Fan-in multi-agent graph.

    Attributes:
        query: User's original question (e.g. analysis request for BTC-USD or NVDA).
        quant_report: Technical/quantitative report produced by Quant_Agent only.
        news_report: News-sentiment report produced by News_Agent only.
        social_report: Retail/social sentiment report produced by Social_Agent only.
        run_id: Per-run identifier (YYYYMMDD_HHMMSS).
        run_dir: Per-run output directory path (data/reports/{run_id}_{asset}/).
        quant_report_obj/news_report_obj/social_report_obj: Structured dicts for CIO bundling.
        quant_report_path/news_report_path/social_report_path/cio_report_path: Report file paths.
        final_decision: Synthesized report from CIO_Agent (no tools).
    """

    query: str
    quant_report: NotRequired[str]
    news_report: NotRequired[str]
    social_report: NotRequired[str]
    run_id: NotRequired[str]
    run_dir: NotRequired[str]
    quant_report_obj: NotRequired[Dict[str, Any]]
    news_report_obj: NotRequired[Dict[str, Any]]
    social_report_obj: NotRequired[Dict[str, Any]]
    quant_report_path: NotRequired[str]
    news_report_path: NotRequired[str]
    social_report_path: NotRequired[str]
    cio_report_path: NotRequired[str]
    final_decision: NotRequired[str]
