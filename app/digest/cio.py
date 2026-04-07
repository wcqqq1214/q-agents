"""Digest-level CIO synthesis helpers."""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.digest.models import CioSummarySection, MacroNewsSection, TechnicalSection
from app.llm_config import create_llm

logger = logging.getLogger(__name__)

DIGEST_CIO_SYSTEM = (
    "You are a CIO writing a concise daily market digest footer. "
    "Return 2 to 4 English sentences covering overall tone, strongest or weakest setups, "
    "and the main macro risk. Stay under 300 tokens."
)


def _compact_cio_prompt(
    technical_sections: list[TechnicalSection],
    macro_news: MacroNewsSection,
) -> str:
    technical_lines = []
    for section in technical_sections:
        technical_lines.append(
            f"{section.get('ticker')}: status={section.get('status')}, trend={section.get('trend')}, summary={section.get('summary')}"
        )
    macro_lines = [f"- {point}" for point in macro_news.get("summary_points", [])]
    return "\n".join(
        [
            "Technical snapshots:",
            *technical_lines,
            "",
            "Macro bullets:",
            *macro_lines,
        ]
    )


def _keep_first_four_sentences(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    compact = " ".join(sentence.strip() for sentence in sentences if sentence.strip()[:1])
    return " ".join(sentences[:4]).strip() or compact


def _fallback_cio_text(
    technical_sections: list[TechnicalSection],
    macro_news: MacroNewsSection,
) -> str:
    available = [section for section in technical_sections if section.get("status") == "ok"]
    bullish = [section["ticker"] for section in available if section.get("trend") == "bullish"]
    bearish = [section["ticker"] for section in available if section.get("trend") == "bearish"]
    unavailable = [
        section["ticker"] for section in technical_sections if section.get("status") != "ok"
    ]
    macro_point = next(iter(macro_news.get("summary_points", [])), "macro visibility is limited")

    tone = "mixed"
    if bullish and not bearish:
        tone = "constructive"
    elif bearish and not bullish:
        tone = "defensive"

    sentences = [
        f"Overall market tone is {tone} across the configured digest universe.",
        (
            f"Stronger setups are {', '.join(bullish[:3])}."
            if bullish
            else "No clear bullish leaders stand out in this run."
        ),
        (
            f"Weaker or unavailable names are {', '.join((bearish + unavailable)[:3])}."
            if bearish or unavailable
            else "Downside pressure is limited in the current snapshot."
        ),
        f"Top macro watchpoint: {macro_point}.",
    ]
    return " ".join(sentences[:4])


def build_cio_summary(
    technical_sections: list[TechnicalSection],
    macro_news: MacroNewsSection,
) -> CioSummarySection:
    """Build the digest-level CIO summary with deterministic length controls.

    Args:
        technical_sections: Ordered technical digest sections for all tickers.
        macro_news: Digest-level macro news summary block.

    Returns:
        CioSummarySection: Concise synthesized view. Falls back to a
        deterministic summary when the configured LLM is unavailable.
    """

    prompt = _compact_cio_prompt(technical_sections, macro_news)
    try:
        llm = create_llm()
        response = llm.invoke(
            [
                SystemMessage(content=DIGEST_CIO_SYSTEM),
                HumanMessage(content=prompt),
            ],
            max_tokens=300,
        )
        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        text = _keep_first_four_sentences(str(content))
        if text:
            return {"status": "ok", "text": text, "error": None}
        raise ValueError("Empty CIO summary response")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falling back to deterministic CIO summary: %s", exc)
        return {
            "status": "ok",
            "text": _fallback_cio_text(technical_sections, macro_news),
            "error": None,
        }
