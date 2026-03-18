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

    - \"NVDA 发布财报大超预期，这次市场会怎么走？\" -> use query like
      ``\"earnings beat\"`` and ticker ``\"NVDA\"``.
    - \"META 宣布大规模裁员，对股价冲击多大？\" -> query ``\"layoffs\"`` and
      ticker ``\"META\"``.
    - \"美联储意外加息时历史上标普的反应\" -> query ``\"rate hike\"`` and
      ticker ``\"^GSPC\"`` (if such events were stored).

    Args:
        query: Short description or keyword capturing the essence of the event,
            such as ``\"earnings miss\"``, ``\"CEO resigns\"`` or
            ``\"interest rate hike\"``. The text can be in English or Chinese.
        ticker: Asset symbol used when building the event memory, for example
            ``\"AAPL\"``, ``\"NVDA\"`` or ``\"META\"``. The tool applies a
            strict metadata filter so that only events for this ticker are
            returned.

    Returns:
        A long-form text in Chinese summarizing up to three historically similar
        events and their realized T+1/T+5 returns. If the underlying vector
        store is empty or no matching events can be found, the function returns
        a short explanatory message instead of raising an exception.

    Disclaimer:
        本工具仅用于研究与教学示例，不构成任何形式的投资建议。历史收益率不代表未来表现，
        在实际投资决策中请结合风险承受能力与专业意见。
    """

    normalized_ticker = (ticker or "").strip().upper()
    normalized_query = (query or "").strip()

    if not normalized_ticker or not normalized_query:
        return (
            "search_historical_event_impact: 需要同时提供非空的 query 和 ticker，"
            "例如 query='earnings beat', ticker='NVDA'。"
        )

    docs = _retrieve_historical_events(
        query=normalized_query,
        ticker=normalized_ticker,
        k=3,
    )
    if not docs:
        return (
            "未能在历史事件记忆库中找到与当前描述高度相似且匹配该标的的事件复盘。"
            "这通常意味着：要么该标的尚未录入足够历史事件，要么这是一个较为新型或罕见的风险情形。"
        )

    parts: List[str] = []
    for idx, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        event_date = meta.get("date", "未知日期")
        event_type = meta.get("event_type", "事件")
        header = f"### 历史事件 {idx}（{normalized_ticker} / {event_type} / {event_date}）"
        parts.append(header)
        parts.append(doc.page_content.rstrip())
        parts.append("")

    parts.append(
        "以上为历史上若干相似事件的真实市场反应，仅供定性与定量参考，"
        "请勿将其视为对未来价格走势的保证。"
    )
    return "\n".join(parts)

