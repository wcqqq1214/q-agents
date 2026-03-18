from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, field_validator

from app.llm_config import create_llm
from app.rag.build_event_memory import (
    create_memory_document,
    EventReturnComputationError,
    fetch_post_event_returns,
    init_chroma_db,
)
from app.tools.finance_tools import NewsItem, _parse_news_published_time, search_news_with_duckduckgo

logger = logging.getLogger(__name__)


def clean_and_parse_llm_json(text: str) -> dict:
    """Robustly parse JSON-like output from an LLM response.

    The parser applies several normalization steps:

    1. Remove any ``<think>...</think>`` reasoning blocks.
    2. Strip markdown code fences such as ```json and ```.
    3. Locate the outermost JSON boundaries using string indices rather than
       regular expressions, so that nested braces/brackets do not cause
       premature truncation.
    4. If the root is a bare array ``[...]``, wrap it into an object of the
       form ``{\"events\": [...]}`` so that it conforms to the :class:`EventList`
       schema expected by the pipeline.
    """

    # 1) Remove any <think>...</think> blocks.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # 2) Remove markdown code fences (```json, ```).
    text = re.sub(r"```", "", text).strip()

    # 3) Replace Chinese quotes with English quotes.
    text = text.replace(""", '"').replace(""", '"')

    # 3) Locate candidate object and array boundaries.
    obj_start = text.find("{")
    obj_end = text.rfind("}")

    arr_start = text.find("[")
    arr_end = text.rfind("]")

    json_str: str

    # Prefer an object root when both are present and the object starts first.
    if obj_start != -1 and obj_end != -1 and (arr_start == -1 or obj_start < arr_start):
        json_str = text[obj_start : obj_end + 1]
    elif arr_start != -1 and arr_end != -1:
        # Root is an array; wrap it into {"events": [...]} for EventList.
        array_str = text[arr_start : arr_end + 1]
        json_str = f'{{"events": {array_str}}}'
    else:
        msg = "Failed to locate valid JSON boundaries in LLM output."
        raise ValueError(msg)

    return json.loads(json_str)


class HistoricalEvent(BaseModel):
    """Structured representation of a single historical event mined from news.

    Notes:
        The schema is intentionally lenient to accommodate different provider
        outputs. Some providers emit a single ``source_index`` field, while
        others use a list of ``source_indices``. Downstream logic collapses
        these into a single canonical index for date and URL resolution. The
        ``date`` field is treated as advisory only; the pipeline always
        recomputes the canonical event date from the linked news item's
        ``published_time`` when possible.
    """

    source_index: Optional[int | List[int] | str] = Field(
        default=None,
        description=(
            "Optional zero-based index of the selected news item from the "
            "provided candidate list. When both ``source_index`` and "
            "``source_indices`` are present, this field takes precedence."
        ),
    )
    source_indices: Optional[List[int]] = Field(
        default=None,
        description=(
            "Optional list of zero-based indices of news items that jointly "
            "support this event. The pipeline typically uses the first element "
            "as the canonical source for date and URL resolution."
        ),
    )
    # Core textual description; we also accept provider-specific fields such
    # as ``headline`` and ``description`` and fold them into this summary
    # during post-processing.
    summary: Optional[str] = Field(
        default=None,
        description=(
            "Objective 1-3 sentence summary describing what happened, grounded "
            "strictly in the referenced news article or articles."
        )
    )
    headline: Optional[str] = Field(
        default=None,
        description=(
            "Optional short headline for the event. When provided, it may be "
            "prepended to the summary during downstream processing."
        ),
    )
    description: Optional[str] = Field(
        default=None,
        description=(
            "Optional alternative field used by some providers instead of "
            "``summary``. When present and ``summary`` is empty, this value "
            "will be used as the primary summary text."
        ),
    )
    event_type: Optional[str] = Field(
        default="news",
        description=(
            "Optional short event category in English or Chinese, such as "
            "'earnings', 'guidance', 'macro', 'management_change', "
            "'product_launch'. Defaults to 'news' when omitted."
        ),
    )
    date: Optional[str] = Field(
        default=None,
        description=(
            "Optional event date string. This field is treated as advisory; the "
            "pipeline derives the canonical date from the linked news item's "
            "published_time whenever possible."
        ),
    )

    @field_validator("source_index", mode="before")
    @classmethod
    def _parse_source_index(
        cls,
        v: Optional[int | List[int] | str],
    ) -> Optional[int]:
        """Normalize ``source_index`` into a single integer if possible.

        This validator is intentionally tolerant of non-canonical outputs from
        LLMs and upstream tools. It accepts:

        - A plain integer (returned as-is).
        - A list of integers or strings (the first element is used).
        - A string representation of an integer, such as ``"0"``.

        Any unparsable or empty input is coerced to ``0`` so downstream logic
        can still perform bounds checking and decide whether to keep or drop
        the event.
        """

        if v is None:
            return None
        # Handle list-style outputs such as [0] or ["0"].
        if isinstance(v, list):
            if not v:
                return 0
            v = v[0]
        # At this point v should be scalar; try to coerce to int.
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0


class EventList(BaseModel):
    """Container for a list of mined historical events."""

    events: List[HistoricalEvent]


@dataclass
class ResolvedEvent:
    """Internal representation of an event fully linked to a concrete news item."""

    date: str
    event_type: str
    summary: str
    source_title: str
    source_url: str
    source_published_time: str


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


def _search_news_for_ticker_year(
    ticker: str,
    year: int,
    max_results: int = 40,
) -> List[NewsItem]:
    """Fetch candidate news articles for a given ticker and calendar year.

    This function uses the existing DuckDuckGo-based MCP-backed search utility
    to retrieve real news articles. Filtering by year is done using the
    ``published_time`` field when it can be parsed; otherwise the item is kept
    as long as the query contains the correct year.
    """

    normalized = _normalize_ticker(ticker)
    if not normalized:
        return []

    queries = [
        f"{normalized} {year} earnings",
        f"{normalized} {year} guidance",
        f"{normalized} {year} downgrade OR upgrade",
        f"{normalized} {year} macro news",
    ]

    collected: Dict[str, NewsItem] = {}
    per_query_limit = max(5, max_results // max(len(queries), 1))

    for q in queries:
        # `search_news_with_duckduckgo` is a LangChain StructuredTool due to @tool.
        # Call it via `.invoke({...})` to avoid treating it like a plain function.
        try:
            items = search_news_with_duckduckgo.invoke(
                {"query": q, "limit": per_query_limit}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "search_news_with_duckduckgo.invoke failed for query=%r: %s",
                q,
                exc,
                exc_info=True,
            )
            continue
        for item in items:
            url = (item.get("url") or "").strip()
            if not url or url in collected:
                continue
            published_raw = item.get("published_time")
            dt = _parse_news_published_time(published_raw)
            if dt is not None and dt.year != year:
                # Skip clearly out-of-year items when date can be parsed.
                continue
            collected[url] = item
            if len(collected) >= max_results:
                break
        if len(collected) >= max_results:
            break

    return list(collected.values())


def _format_news_context(news: Sequence[NewsItem]) -> str:
    """Render candidate news items as numbered plain-text context for the LLM."""

    lines: List[str] = []
    for idx, item in enumerate(news):
        title = item.get("title") or ""
        snippet = item.get("snippet") or ""
        published = item.get("published_time") or ""
        source = item.get("source") or ""
        lines.append(f"[{idx}] title={title}")
        if source:
            lines.append(f"    source={source}")
        if published:
            lines.append(f"    published_time={published}")
        if snippet:
            lines.append(f"    snippet={snippet}")
        lines.append("")
    return "\n".join(lines)


def _get_llm():
    """Return a ChatOpenAI instance configured from environment variables."""
    temperature_str = os.getenv("LLM_TEMPERATURE", "0.0")
    try:
        temperature = float(temperature_str)
    except ValueError:
        temperature = 0.0
    return create_llm(temperature=temperature)


def _parse_event_list_from_content(raw_content: str) -> Optional[EventList]:
    """Parse :class:`EventList` from an arbitrary LLM response string.

    The function delegates JSON boundary detection and normalization to
    :func:`clean_and_parse_llm_json`. It returns ``None`` when parsing or
    validation fails so that the caller can fall back gracefully.
    """

    if not raw_content:
        return None

    try:
        data = clean_and_parse_llm_json(raw_content)
        return EventList.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to parse EventList JSON from content: %r (%s)",
            raw_content,
            exc,
        )
        return None


def mine_historical_events(ticker: str, year: int) -> List[ResolvedEvent]:
    """Mine major historical events for a ticker-year pair using LLM + news search.

    The function strictly enforces the following invariants:

    1. All returned events are **grounded in real news articles** obtained via
       DuckDuckGo search; no hallucinated URLs or dates are accepted.
    2. Each event is linked to a concrete ``NewsItem`` via ``source_index``.
    3. The final event date is derived from the authoritative news
       ``published_time`` (when parseable) or, as a fallback, from the
       specified calendar year.

    Args:
        ticker: Asset symbol, for example ``\"NVDA\"`` or ``\"AAPL\"``.
        year: Calendar year (e.g. ``2024``) to search within.

    Returns:
        A list of :class:`ResolvedEvent` instances which can be directly used to
        build fused memory documents and feed into the Chroma event database.
        The list may be empty if no reliable events can be mined.
    """

    normalized = _normalize_ticker(ticker)
    if not normalized:
        return []

    news_items = _search_news_for_ticker_year(normalized, year)
    if not news_items:
        logger.info("mine_historical_events: no news candidates for %s %s", normalized, year)
        return []

    context = _format_news_context(news_items)
    llm = _get_llm()

    system_prompt = (
        "You are a meticulous equity research analyst. You are given a list of "
        "real news articles about a single asset and a specific calendar year. "
        "Your task is to select 5-10 truly significant events that caused or "
        "were associated with large price moves, and summarize them.\n\n"
        "CRITICAL RULES:\n"
        "1. You MUST only use the provided news list. Do NOT invent events, "
        "   dates, tickers, URLs or sources.\n"
        "2. For each event you output, you MUST reference an existing news "
        "   item by its zero-based index `source_index`.\n"
        "3. If you are unsure whether an article corresponds to a major price "
        "   move, you may skip it; less is better than hallucination.\n"
        "4. Summaries must be objective and free of speculation.\n"
        "5. For any given news article (identified by its index / URL), you MUST "
        "   output at most one event. Do NOT generate multiple separate events "
        "   that all reference the same article; instead, merge the key aspects "
        "   into a single concise event.\n\n"
        "OUTPUT FORMAT RULES (STRICT):\n"
        "- Output strictly in valid JSON format that matches the EventList schema.\n"
        "- Do not include markdown formatting such as ```json or any code fences.\n"
        "- You MUST output a valid JSON object. The root MUST be an object "
        'containing a single key "events", whose value is a list of event '
        "objects. DO NOT output a raw list/array at the root level.\n"
        "- The field \"source_index\" MUST be a single integer (e.g., 0). "
        "DO NOT use arrays or lists like [0].\n"
        "- Do not output any thinking process, reasoning trace, conversational "
        "text, or explanations. Only return the JSON object."
    )

    user_prompt = (
        f"Ticker: {normalized}\n"
        f"Year: {year}\n\n"
        "Below is the list of candidate news articles. Each has a numeric index "
        "in square brackets. Use these indices in your structured output:\n\n"
        f"{context}\n\n"
        "Now select 5-10 of the most important events for this ticker and year. "
        "Return them strictly in the JSON schema provided (EventList) as a "
        "single JSON object. Do not include <think> blocks, markdown code "
        "fences, or any additional natural-language explanations."
    )

    try:
        msg = llm.invoke(
            [
                ("system", system_prompt),
                ("user", user_prompt),
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "mine_historical_events: LLM call failed for %s %s: %s",
            normalized,
            year,
            exc,
            exc_info=True,
        )
        return []

    content = getattr(msg, "content", "")  # ChatOpenAI returns a BaseMessage-like object
    if isinstance(content, list):
        # Some drivers may return a list of content parts; join them if so.
        content = "".join(str(part) for part in content)

    event_list = _parse_event_list_from_content(str(content))
    if event_list is None:
        logger.warning(
            "mine_historical_events: could not parse structured EventList for %s %s; "
            "raw content was: %r",
            normalized,
            year,
            content,
        )
        return []

    resolved: List[ResolvedEvent] = []
    for event in event_list.events:
        idx: Optional[int] = None

        # Prefer explicit single index when present.
        if event.source_index is not None:
            idx = event.source_index
        # Fall back to the first element of source_indices, if provided.
        elif event.source_indices:
            try:
                idx = event.source_indices[0]
            except Exception:
                idx = None

        if idx is None or idx < 0 or idx >= len(news_items):
            logger.info(
                "mine_historical_events: skipping event with invalid indices=%r for %s %s",
                {
                    "source_index": event.source_index,
                    "source_indices": event.source_indices,
                },
                normalized,
                year,
            )
            continue

        source = news_items[idx]
        published_raw = source.get("published_time")
        dt = _parse_news_published_time(published_raw)
        if dt is None:
            # Fallback: trust the specified year, defaulting to mid-year.
            date_str = f"{year}-06-30"
        else:
            date_str = dt.date().isoformat()

        title = source.get("title") or ""
        url = source.get("url") or ""
        event_type = (event.event_type or "news").strip() or "news"

        # Build a robust summary by folding headline/description into summary.
        raw_summary: str = ""
        if event.summary:
            raw_summary = event.summary
        elif event.description:
            raw_summary = event.description

        raw_summary = (raw_summary or "").strip()
        if event.headline:
            headline_clean = event.headline.strip()
            if headline_clean:
                # Prepend headline as a short label if not already contained.
                if raw_summary:
                    raw_summary = f"{headline_clean} — {raw_summary}"
                else:
                    raw_summary = headline_clean

        if not raw_summary:
            logger.info(
                "mine_historical_events: skipping event without usable summary for %s %s (indices=%r)",
                normalized,
                year,
                {
                    "source_index": event.source_index,
                    "source_indices": event.source_indices,
                },
            )
            continue

        resolved.append(
            ResolvedEvent(
                date=date_str,
                event_type=event_type,
                summary=raw_summary,
                source_title=title.strip(),
                source_url=url.strip(),
                source_published_time=published_raw or "",
            )
        )

    return resolved


def _build_event_document(
    ticker: str,
    resolved_event: ResolvedEvent,
    returns: Dict[str, float],
) -> Tuple[str, Dict[str, str]]:
    """Create fused memory text and metadata for a single resolved event."""

    base_doc = create_memory_document(
        ticker=ticker,
        date=resolved_event.date,
        news_summary=resolved_event.summary,
        returns=returns,
    )

    # Append a short source note so future consumers understand provenance.
    source_note = (
        "数据来源：该事件由基于 DuckDuckGo 的新闻检索与大模型摘要自动挖掘，"
        "并通过 yfinance 行情计算 T+1/T+5 收益率；仅供研究参考，不构成投资建议。\n"
        f"代表性新闻标题：{resolved_event.source_title}\n"
        f"新闻链接：{resolved_event.source_url}\n"
    )
    full_doc = base_doc + "\n" + source_note

    metadata: Dict[str, str] = {
        "ticker": _normalize_ticker(ticker),
        "date": resolved_event.date,
        "event_type": resolved_event.event_type or "news",
        "source_url": resolved_event.source_url,
        "source_title": resolved_event.source_title,
    }
    return full_doc, metadata


def build_and_store_memory(
    ticker: str,
    years: Sequence[int],
    persist_directory: str = "./chroma_event_db",
) -> None:
    """End-to-end pipeline: mine events, compute returns, and persist to Chroma.

    This function is intended to be run offline for a single ticker across
    multiple recent years. It composes:

    1. News search + LLM-based event mining (:func:`mine_historical_events`).
    2. Post-event return computation (:func:`fetch_post_event_returns`).
    3. Fused memory document construction (:func:`create_memory_document`).
    4. Local ChromaDB persistence (:func:`init_chroma_db`).
    """

    normalized = _normalize_ticker(ticker)
    if not normalized:
        logger.warning("build_and_store_memory: empty ticker; aborted.")
        return

    docs: List[str] = []
    metadatas: List[Dict[str, str]] = []
    # For de-duplication at the (ticker, source_url) level. Each value is
    # (doc, metadata, doc_length).
    best_by_url: Dict[Tuple[str, str], Tuple[str, Dict[str, str], int]] = {}

    for year in years:
        mined_events = mine_historical_events(normalized, year)
        if not mined_events:
            logger.info("No mined events for %s in %s", normalized, year)
            continue

        for ev in mined_events:
            try:
                returns = fetch_post_event_returns(normalized, ev.date)
            except EventReturnComputationError as exc:
                logger.warning(
                    "build_and_store_memory: skip event %s %s due to return calc error: %s",
                    normalized,
                    ev.date,
                    exc,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "build_and_store_memory: skip event %s %s due to return calc error: %s",
                    normalized,
                    ev.date,
                    exc,
                    exc_info=True,
                )
                continue

            doc, meta = _build_event_document(normalized, ev, returns)
            doc_clean = (doc or "").strip()
            if not doc_clean:
                logger.info(
                    "build_and_store_memory: skipping empty document for %s %s",
                    normalized,
                    ev.date,
                )
                continue

            source_url = (meta.get("source_url") or "").strip()
            dedupe_key = (normalized, source_url) if source_url else (normalized, f"__no_url__:{ev.date}:{ev.summary[:32]}")

            current_len = len(doc_clean)
            existing = best_by_url.get(dedupe_key)
            if existing is None or current_len > existing[2]:
                best_by_url[dedupe_key] = (doc_clean, meta, current_len)

    if not best_by_url:
        logger.warning(
            "build_and_store_memory: no documents to persist for %s; "
            "skipping Chroma insertion to avoid empty embedding requests.",
            normalized,
        )
        return

    # Flatten the de-duplicated mapping into docs/metadatas lists.
    deduped_docs: List[str] = []
    deduped_metadatas: List[Dict[str, str]] = []
    for doc_clean, meta, _ in best_by_url.values():
        deduped_docs.append(doc_clean)
        deduped_metadatas.append(meta)

    init_chroma_db(
        docs=deduped_docs,
        metadatas=deduped_metadatas,
        persist_directory=persist_directory,
    )


def main() -> None:
    """Minimal manual entrypoint for building the LLM-based event memory DB.

    By default this function:

    - Targets a fixed list of liquid US equities and ETFs:
      NVDA, MSFT, TSLA, AAPL, GOOG, META, AMZN, QQQ, VOO.
    - Covers the most recent 5 calendar years up to the current year.
    - Prints a short JSON summary of how many events were built per ticker.
    """

    tickers = ["NVDA", "MSFT", "TSLA", "AAPL", "GOOG", "META", "AMZN", "QQQ", "VOO"]
    current_year = datetime.utcnow().year
    years = list(range(current_year - 4, current_year + 1))

    summary: Dict[str, Dict[str, int]] = {}
    for ticker in tickers:
        before_docs: int = 0
        try:
            build_and_store_memory(ticker=ticker, years=years)
            # We do not track individual doc counts here because
            # Chroma's low-level API is not necessary for a quick summary.
            summary[ticker] = {"status": 1}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "main: build_and_store_memory failed for %s: %s",
                ticker,
                exc,
                exc_info=True,
            )
            summary[ticker] = {"status": 0}

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

