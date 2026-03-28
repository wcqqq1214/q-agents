"""Layer 1: LLM semantic extraction — 50 articles per API call.

Strategy:
1. Pack 50 articles into a single prompt → 1 API call
2. Extract: relevance, sentiment, key_discussion, reason_growth, reason_decrease
3. Use configured LLM provider
"""

import json
import logging
import os
import time
from typing import Any, Dict, List

import anthropic

from app.database import get_conn
from app.llm_config import create_llm

logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # articles per API call
MAX_RETRIES = 3  # maximum retry attempts for failed batches
RETRY_DELAY = 5  # seconds to wait between retries


def _make_llm():
    """Create LLM client for Layer 1 processing."""
    return create_llm()


def _build_batch_prompt(symbol: str, articles: List[Dict[str, Any]]) -> str:
    """Build a single prompt containing up to 50 articles."""
    lines = []
    for i, art in enumerate(articles):
        lines.append(f"[{i}] {art['title']}")
        if art.get("description"):
            lines.append(f"  > {art['description'][:500]}")

    return f"""Analyze these {len(articles)} news articles for {symbol}. Return one line per article.

{chr(10).join(lines)}

For each article, return ONE line in this exact format:
INDEX|RELEVANT|SENTIMENT|SUMMARY|UP_REASON|DOWN_REASON

- INDEX: article number (0-{len(articles) - 1})
- RELEVANT: Y if article specifically discusses {symbol} company/stock, N if irrelevant
- SENTIMENT: + for positive, - for negative, 0 for neutral
- SUMMARY: brief 5-10 word summary (use NONE if irrelevant)
- UP_REASON: why this could push {symbol} UP (use NONE if none)
- DOWN_REASON: why this could push {symbol} DOWN (use NONE if none)

IMPORTANT:
- Use pipe | as separator
- No pipes inside the text fields
- Return exactly {len(articles)} lines
- No extra text, no explanations

Output:"""


def get_pending_articles(symbol: str, limit: int = 10000) -> List[Dict[str, Any]]:
    """Get articles that passed Layer 0 but haven't been processed by Layer 1."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT n.id, n.title, n.description
           FROM news n
           JOIN layer0_results l0 ON n.id = l0.news_id AND l0.symbol = ?
           WHERE l0.passed = 1
           AND n.id NOT IN (
               SELECT news_id FROM layer1_results WHERE symbol = ?
           )
           LIMIT ?""",
        (symbol, symbol, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def process_batch_group(symbol: str, articles: List[Dict[str, Any]]) -> Dict[str, int]:
    """Process a group of up to 50 articles in a single API call."""
    llm = _make_llm()
    conn = get_conn()

    stats = {"processed": 0, "relevant": 0, "irrelevant": 0, "errors": 0}

    prompt = _build_batch_prompt(symbol, articles)

    try:
        # Handle both LangChain and native Anthropic clients
        if isinstance(llm, anthropic.Anthropic):
            # Native Anthropic API
            model = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
            response = llm.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
        else:
            # LangChain client (OpenAI-compatible)
            response = llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)

        # Parse pipe-delimited output
        lines = text.strip().split("\n")
        results = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("INDEX"):
                continue  # Skip empty lines, comments, and header

            parts = line.split("|")
            if len(parts) < 3:  # At least need index, relevant, sentiment
                logger.warning(f"Skipping malformed line (too few fields): {line[:100]}")
                continue

            try:
                idx = int(parts[0].strip())
                relevant = parts[1].strip().upper()
                sentiment = parts[2].strip() if len(parts) > 2 else "0"
                summary = parts[3].strip() if len(parts) > 3 else ""
                up_reason = parts[4].strip() if len(parts) > 4 else ""
                down_reason = parts[5].strip() if len(parts) > 5 else ""

                if idx < 0 or idx >= len(articles):
                    logger.warning(f"Invalid index {idx}, skipping")
                    continue

                results.append(
                    {
                        "i": idx,
                        "r": "y" if relevant == "Y" else "n",
                        "s": sentiment,
                        "e": "" if summary.upper() == "NONE" else summary,
                        "u": "" if up_reason.upper() == "NONE" else up_reason,
                        "d": "" if down_reason.upper() == "NONE" else down_reason,
                    }
                )
            except (ValueError, IndexError) as e:
                logger.warning(f"Error parsing line: {line[:100]} - {e}")
                continue

        for item in results:
            idx = item.get("i")
            if idx is None or idx >= len(articles):
                stats["errors"] += 1
                continue

            art = articles[idx]
            is_relevant = item.get("r") in ("y", "relevant")
            relevance = "relevant" if is_relevant else "irrelevant"
            raw_s = item.get("s", "0")
            sentiment = {"+": "positive", "-": "negative"}.get(raw_s, "neutral")

            conn.execute(
                """INSERT OR REPLACE INTO layer1_results
                   (news_id, symbol, relevance, key_discussion, sentiment,
                    reason_growth, reason_decrease)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    art["id"],
                    symbol,
                    relevance,
                    item.get("e", ""),
                    sentiment,
                    item.get("u", ""),
                    item.get("d", ""),
                ),
            )
            stats["processed"] += 1
            if is_relevant:
                stats["relevant"] += 1
            else:
                stats["irrelevant"] += 1

        # Commit after successful processing
        conn.commit()

    except (json.JSONDecodeError, KeyError, Exception) as e:
        stats["errors"] = len(articles)
        logger.error(f"Batch error for {symbol}: {e}")
        # Rollback on error to ensure clean state
        conn.rollback()
    finally:
        # Always close the connection
        conn.close()

    return stats


def run_layer1(symbol: str, max_articles: int = 10000) -> Dict[str, Any]:
    """Run Layer 1 on all pending articles for a symbol.

    Processes in groups of 50 articles per API call with automatic retry
    for failed batches.

    Args:
        symbol: Stock ticker symbol.
        max_articles: Maximum number of articles to process.

    Returns:
        Dictionary with processing statistics.
    """
    articles = get_pending_articles(symbol, limit=max_articles)
    if not articles:
        return {"status": "no_pending", "total": 0}

    total_stats = {
        "total": len(articles),
        "processed": 0,
        "relevant": 0,
        "irrelevant": 0,
        "errors": 0,
        "api_calls": 0,
        "retries": 0,
    }

    for i in range(0, len(articles), BATCH_SIZE):
        chunk = articles[i : i + BATCH_SIZE]
        batch_num = total_stats["api_calls"] + 1

        # Retry logic for failed batches
        for attempt in range(MAX_RETRIES):
            stats = process_batch_group(symbol, chunk)
            total_stats["api_calls"] += 1

            # Check if batch failed completely (no articles processed)
            if stats["processed"] == 0 and stats["errors"] > 0:
                if attempt < MAX_RETRIES - 1:
                    total_stats["retries"] += 1
                    logger.warning(
                        f"[{symbol}] Batch {batch_num} failed (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {RETRY_DELAY}s..."
                    )
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    logger.error(
                        f"[{symbol}] Batch {batch_num} failed after {MAX_RETRIES} attempts, skipping"
                    )

            # Batch succeeded or partially succeeded, update stats and break
            total_stats["processed"] += stats["processed"]
            total_stats["relevant"] += stats["relevant"]
            total_stats["irrelevant"] += stats["irrelevant"]
            total_stats["errors"] += stats["errors"]

            logger.info(
                f"[{symbol}] Batch {batch_num}: "
                f"{stats['processed']}/{len(chunk)} ok, {stats['relevant']} relevant"
                + (f" (retry {attempt + 1})" if attempt > 0 else "")
            )
            break

    return total_stats
