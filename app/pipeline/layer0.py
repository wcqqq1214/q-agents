"""Layer 0: Rule-based filter (free, instant).

Filters out clearly irrelevant news before sending to LLM.
Expected: ~25-35% rejection at zero cost.
"""

import logging
import re
from typing import Dict, Tuple

from app.database import get_conn

logger = logging.getLogger(__name__)

# Patterns for list articles
LIST_PATTERN = re.compile(
    r"^\d+\s+(best|top|worst|biggest|largest|most|highest|lowest)\b",
    re.IGNORECASE,
)
LIST_PATTERN_2 = re.compile(r"\b(top|best|worst)\s+\d+\b", re.IGNORECASE)


def _check_article(
    title: str,
    description: str | None,
    symbol: str,
) -> Tuple[bool, str]:
    """Check if article should proceed to Layer 1.

    Args:
        title: Article title.
        description: Article description/summary.
        symbol: Target stock symbol.

    Returns:
        Tuple of (passed, reason). passed=True means article should proceed to Layer 1.
    """
    desc = (description or "").strip()

    # Rule 1: Empty description
    if not desc:
        return False, "empty_description"

    # Rule 2: Description too short (just a title repeat)
    if len(desc) < 30:
        return False, "description_too_short"

    # Rule 3: List articles
    t = (title or "").strip()
    if LIST_PATTERN.search(t) or LIST_PATTERN_2.search(t):
        return False, "list_article"

    return True, "passed"


def run_layer0(symbol: str) -> Dict[str, int]:
    """Run Layer 0 on all unprocessed news for a symbol.

    Args:
        symbol: Stock ticker symbol.

    Returns:
        Dictionary with filter statistics:
        - total: Total articles processed
        - passed: Articles that passed filter
        - filtered: Articles that were filtered out
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, title, description
               FROM news
               WHERE symbol = ?
               AND id NOT IN (
                   SELECT news_id FROM layer0_results WHERE symbol = ?
               )""",
            (symbol, symbol),
        ).fetchall()

        stats = {"total": len(rows), "passed": 0, "filtered": 0}

        for row in rows:
            passed, reason = _check_article(row["title"], row["description"], symbol)
            conn.execute(
                "INSERT OR IGNORE INTO layer0_results (news_id, symbol, passed, reason) VALUES (?, ?, ?, ?)",
                (row["id"], symbol, 1 if passed else 0, reason),
            )
            if passed:
                stats["passed"] += 1
            else:
                stats["filtered"] += 1

        conn.commit()
        logger.info(f"Layer 0 for {symbol}: {stats['passed']}/{stats['total']} passed")
        return stats
    except Exception as exc:
        logger.error(f"Failed to run layer0 for {symbol}: {exc}")
        conn.rollback()
        return {"total": 0, "passed": 0, "filtered": 0}
    finally:
        conn.close()
