"""LLM configuration module."""

from __future__ import annotations

import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()


def create_llm(temperature: float = 0.0) -> ChatAnthropic:
    """Create Claude LLM instance."""
    api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY or ANTHROPIC_API_KEY is not set.")

    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
    base_url = os.environ.get("CLAUDE_BASE_URL")

    kwargs = {"model": model, "api_key": api_key, "temperature": temperature}
    if base_url:
        kwargs["base_url"] = base_url

    return ChatAnthropic(**kwargs)
