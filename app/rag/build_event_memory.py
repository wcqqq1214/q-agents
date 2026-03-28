from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pandas as pd
import yfinance as yf
from langchain_chroma import Chroma

from app.embedding_config import create_embeddings

logger = logging.getLogger(__name__)


class EventReturnComputationError(Exception):
    """Raised when post-event return computation fails due to missing data."""


@dataclass
class PostEventReturns:
    """Container for post-event returns.

    Attributes:
        t1_return: Next trading day's close-to-close return relative to event
            close (T+1).
        t5_return: Fifth trading day's cumulative close-to-close return
            relative to event close (T+5).
    """

    t1_return: float
    t5_return: float


def _parse_event_date(date: str) -> datetime:
    """Parse an ISO-like event date string into a timezone-aware UTC datetime."""

    try:
        dt = datetime.fromisoformat(date)
    except ValueError as exc:
        msg = f"Invalid event date format {date!r}; expected 'YYYY-MM-DD'."
        raise EventReturnComputationError(msg) from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _select_trading_indices(
    history: pd.DataFrame, event_dt: datetime
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """Select event, T+1 and T+5 trading-day indices from a price history."""

    if history.empty or "Close" not in history.columns:
        msg = "Price history is empty or missing 'Close' column."
        raise EventReturnComputationError(msg)

    idx = history.index.sort_values()
    # Align event date to the first index >= event_dt (handle holidays/weekends).
    event_idx_candidates = idx[idx >= event_dt]
    if len(event_idx_candidates) == 0:
        msg = "No trading session on or after event date; cannot compute post-event returns."
        raise EventReturnComputationError(msg)

    event_idx = event_idx_candidates[0]
    event_pos = idx.get_loc(event_idx)

    if event_pos + 1 >= len(idx) or event_pos + 5 >= len(idx):
        msg = (
            "Insufficient forward trading days after event to compute T+1/T+5 "
            f"returns; have {len(idx) - event_pos - 1} days."
        )
        raise EventReturnComputationError(msg)

    t1_idx = idx[event_pos + 1]
    t5_idx = idx[event_pos + 5]
    return event_idx, t1_idx, t5_idx


def fetch_post_event_returns(ticker: str, date: str) -> Dict[str, float]:
    """Compute T+1 and T+5 post-event returns using Yahoo Finance data.

    This helper pulls a small price window around the event date and computes
    simple close-to-close returns for the next trading day (T+1) and the fifth
    trading day (T+5). It is intended for building fused memory documents and
    is not suitable for intraday or high-precision backtesting.

    Args:
        ticker: Asset symbol understood by Yahoo Finance (for example, ``\"META\"``
            or ``\"NVDA\"``). The symbol is internally uppercased.
        date: Event date in ``\"YYYY-MM-DD\"`` format. If the date falls on a
            non-trading day, the computation will align to the next available
            trading session.

    Returns:
        A dictionary with keys:

        - ``\"t1_return\"``: Next-trading-day close-to-close return.
        - ``\"t5_return\"``: Fifth-trading-day cumulative close-to-close return.

    Raises:
        EventReturnComputationError: If historical prices are missing or there
            are not enough forward trading days to compute the requested
            horizons.
    """

    normalized = (ticker or "").strip().upper()
    if not normalized:
        msg = "ticker is empty; cannot compute post-event returns."
        raise EventReturnComputationError(msg)

    event_dt = _parse_event_date(date)
    # Fetch a window around the event to avoid large downloads while still
    # allowing T+1/T+5 to naturally cross year boundaries. Using a 40-day
    # forward window makes it very unlikely that we run out of trading days
    # due to holidays or year-end closures.
    start = (event_dt - timedelta(days=5)).date().isoformat()
    end = (event_dt + timedelta(days=40)).date().isoformat()

    try:
        history = yf.Ticker(normalized).history(start=start, end=end, auto_adjust=False)
    except Exception as exc:  # noqa: BLE001
        msg = f"Failed to fetch history for {normalized}: {type(exc).__name__}: {exc}"
        logger.warning("fetch_post_event_returns failed: %s", msg, exc_info=True)
        raise EventReturnComputationError(msg) from exc

    event_idx, t1_idx, t5_idx = _select_trading_indices(history, event_dt)

    p0 = float(history.loc[event_idx, "Close"])
    p1 = float(history.loc[t1_idx, "Close"])
    p5 = float(history.loc[t5_idx, "Close"])

    if p0 <= 0.0:
        msg = "Event-day close price is non-positive; cannot compute returns."
        raise EventReturnComputationError(msg)

    t1_ret = (p1 - p0) / p0
    t5_ret = (p5 - p0) / p0

    return {"t1_return": float(t1_ret), "t5_return": float(t5_ret)}


def create_memory_document(
    ticker: str,
    date: str,
    news_summary: str,
    returns: Dict[str, float],
) -> str:
    """Create a fused memory text block for a single historical event.

    The output follows the blueprint's ``【历史事件复盘】`` template so that both
    humans and LLMs can quickly understand the asset, date, event description
    and realized post-event returns.

    Args:
        ticker: Asset ticker such as ``\"META\"`` or ``\"NVDA\"``.
        date: Event date as ``\"YYYY-MM-DD\"``.
        news_summary: Short Chinese or English summary of the event (for
            example, earnings surprise, management change, macro shock).
        returns: Dictionary containing at least keys ``\"t1_return\"`` and
            ``\"t5_return\"`` as decimal returns (e.g. ``0.12`` for ``12%``).

    Returns:
        A multi-line string suitable for direct ingestion into a vector store.
    """

    normalized_ticker = (ticker or "").strip().upper()
    summary = (news_summary or "").strip()
    t1 = float(returns.get("t1_return", 0.0))
    t5 = float(returns.get("t5_return", 0.0))

    lines: List[str] = [
        "【历史事件复盘】",
        f"标的：{normalized_ticker}",
        f"日期：{date}",
        f"事件摘要：{summary}",
        "市场真实反应：",
        f"- 次日(T+1)真实收益率：{t1:.2%}",
        f"- 后续(T+5)累计收益率：{t5:.2%}",
        "",
    ]
    return "\n".join(lines)


def init_chroma_db(
    docs: List[str],
    metadatas: List[Dict[str, str]],
    persist_directory: str = "./chroma_db",
) -> None:
    """Initialize or overwrite a local ChromaDB event memory store.

    This helper builds a persistent Chroma vector store using MiniMax-compatible
    embeddings. It is intended to be called from offline scripts or tests that
    prepare the event-driven fused memory blocks before they are consumed by
    agents via RAG tools.

    Args:
        docs: List of fused memory texts, one per historical event.
        metadatas: List of metadata dictionaries aligned with ``docs``. Each
            entry must contain at least ``\"ticker\"``, ``\"date\"`` and
            ``\"event_type\"`` keys so that downstream retrievers can filter by
            asset and event category.
        persist_directory: Filesystem directory where the Chroma index should
            be stored. Defaults to ``\"./chroma_db\"`` and can be overridden in
            tests or specialized pipelines.

    Raises:
        ValueError: If the lengths of ``docs`` and ``metadatas`` do not match.
    """

    if len(docs) != len(metadatas):
        msg = f"docs and metadatas length mismatch: {len(docs)} vs {len(metadatas)}."
        raise ValueError(msg)

    if not docs:
        logger.info("init_chroma_db called with empty docs; nothing to store.")
        return

    # 1. 终极清理：过滤掉全空格、空字符串，防止 docs = [\"\", \" \"] 骗过校验
    cleaned_docs: List[str] = []
    cleaned_metadatas: List[Dict[str, str]] = []

    if docs:
        for doc, meta in zip(docs, metadatas, strict=True):
            if doc and doc.strip():
                cleaned_docs.append(doc)
                cleaned_metadatas.append(meta)

    # 2. 严格拦截：如果清理后没东西了，绝对不再往下走
    if not cleaned_docs:
        print(
            "init_chroma_db: No valid text content to embed; "
            "skipping this batch to avoid API crash."
        )
        return

    # Use configured embedding provider
    embeddings = create_embeddings()

    # Create or get existing collection with correct embedding function
    db = Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings,
        collection_name="event_memory",
    )

    # Add documents in batches
    batch_size = 100
    for i in range(0, len(cleaned_docs), batch_size):
        batch_docs = cleaned_docs[i : i + batch_size]
        batch_metas = cleaned_metadatas[i : i + batch_size] if cleaned_metadatas else None
        db.add_texts(texts=batch_docs, metadatas=batch_metas)
        logger.info(
            f"Added batch {i // batch_size + 1}/{(len(cleaned_docs) - 1) // batch_size + 1}"
        )


def build_sample_memory(
    samples: List[Dict[str, str]],
    persist_directory: str = "./chroma_db",
) -> None:
    """Build a small sample event memory store from in-memory records.

    This convenience function is primarily intended for manual experiments and
    tests. Each sample should contain fields:

    - ``\"ticker\"``: Asset symbol.
    - ``\"date\"``: Event date (``\"YYYY-MM-DD\"``).
    - ``\"news_summary\"``: Short textual description of the event.
    - ``\"event_type\"``: Category such as ``\"earnings\"`` or ``\"macro\"``.

    For each record the function will:

    1. Compute post-event returns via :func:`fetch_post_event_returns`.
    2. Create a fused memory document via :func:`create_memory_document`.
    3. Persist all documents into a local Chroma store.

    Args:
        samples: List of small dictionaries describing historical events.
        persist_directory: Target directory for ChromaDB storage.
    """

    docs: List[str] = []
    metadatas: List[Dict[str, str]] = []

    for sample in samples:
        ticker = sample["ticker"]
        date = sample["date"]
        news_summary = sample["news_summary"]
        event_type = sample.get("event_type", "news")

        rets = fetch_post_event_returns(ticker=ticker, date=date)
        doc = create_memory_document(
            ticker=ticker,
            date=date,
            news_summary=news_summary,
            returns=rets,
        )
        docs.append(doc)
        metadatas.append(
            {
                "ticker": ticker,
                "date": date,
                "event_type": event_type,
            }
        )

    init_chroma_db(docs=docs, metadatas=metadatas, persist_directory=persist_directory)
