from __future__ import annotations

import logging
import os
from typing import List

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.tools import tool

from app.embedding_config import create_embeddings

logger = logging.getLogger(__name__)

DEFAULT_EVENT_MEMORY_DIR = "./chroma_db"


def _get_event_memory_directory() -> str:
    """Return the filesystem directory where the event memory Chroma store lives."""

    return os.getenv("EVENT_MEMORY_DB_DIR", DEFAULT_EVENT_MEMORY_DIR)


def _load_event_memory_store() -> Chroma:
    """Load the persistent Chroma event memory store.

    Returns:
        A ``Chroma`` vector store instance pointing at the event memory
        collection. The function assumes that the underlying directory has
        already been populated by :func:`init_chroma_db`.
    """

    persist_directory = _get_event_memory_directory()
    embeddings = create_embeddings()

    return Chroma(
        embedding_function=embeddings,
        persist_directory=persist_directory,
        collection_name="event_memory",
    )


def _retrieve_historical_events(query: str, ticker: str, k: int = 3) -> List[Document]:
    """Retrieve top-k historical event documents for a given ticker."""

    store = _load_event_memory_store()
    try:
        results = store.similarity_search(
            query=query,
            k=k,
            filter={"ticker": ticker},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "search_historical_event_impact similarity_search failed: %s",
            exc,
            exc_info=True,
        )
        return []
    return results


@tool("search_historical_event_impact")
def search_historical_event_impact(query: str, ticker: str) -> str:
    """Search historical event memory to understand realized market impact.

    This tool is designed for **News / CIO Agents** that need concrete
    historical references when confronted with a new piece of news such as an
    earnings surprise, management change or macro data release. Given a free
    text description of the event and a specific ticker, it retrieves fused
    memory blocks summarizing similar past events and their realized returns.

    Typical usage examples:

    - \"NVDA reported a major earnings beat. How did the market usually react?\"
      -> use query ``\"earnings beat\"`` and ticker ``\"NVDA\"``.
    - \"META announced large layoffs. How large was the historical stock impact?\"
      -> use query ``\"layoffs\"`` and ticker ``\"META\"``.
    - \"How did the S&P 500 react to surprise Fed rate hikes in the past?\"
      -> use query ``\"rate hike\"`` and ticker ``\"^GSPC\"`` (if such events
      were stored).

    Args:
        query: Short description or keyword capturing the essence of the event,
            such as ``\"earnings miss\"``, ``\"CEO resigns\"`` or
            ``\"interest rate hike\"``.
        ticker: Asset symbol used when building the event memory, for example
            ``\"AAPL\"``, ``\"NVDA\"`` or ``\"META\"``. The tool applies a
            strict metadata filter so that only events for this ticker are
            returned.

    Returns:
        A long-form text in English summarizing up to three historically similar
        events and their realized T+1/T+5 returns. If the underlying vector
        store is empty or no matching events can be found, the function returns
        a short explanatory message instead of raising an exception.

    Disclaimer:
        This tool is provided for research and educational use only. Historical
        returns do not guarantee future performance and are not investment
        advice.
    """

    normalized_ticker = (ticker or "").strip().upper()
    normalized_query = (query or "").strip()

    if not normalized_ticker or not normalized_query:
        return (
            "search_historical_event_impact requires non-empty query and ticker "
            "inputs, for example query='earnings beat', ticker='NVDA'."
        )

    docs = _retrieve_historical_events(
        query=normalized_query,
        ticker=normalized_ticker,
        k=3,
    )
    if not docs:
        return (
            "No closely matching historical events were found in the event "
            "memory for this ticker. This usually means either the ticker does "
            "not yet have enough stored events or the current situation is a "
            "new or relatively rare scenario."
        )

    parts: List[str] = []
    for idx, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        event_date = meta.get("date", "unknown date")
        event_type = meta.get("event_type", "event")
        header = f"### Historical Event {idx} ({normalized_ticker} / {event_type} / {event_date})"
        parts.append(header)
        parts.append(doc.page_content.rstrip())
        parts.append("")

    parts.append(
        "These examples summarize realized market reactions from similar "
        "historical events and are provided for qualitative and quantitative "
        "reference only. Do not treat them as a guarantee of future price action."
    )
    return "\n".join(parts)
