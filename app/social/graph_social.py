"""Social Agent LangGraph: Reddit ingestion -> LLM NLP -> report export.

This graph is intended to be called by the CIO (or an upstream orchestrator),
not by an end user directly.
"""

from __future__ import annotations

import json
from typing import List, Optional, Sequence, cast

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.social.export_tools import build_social_report, save_social_report
from app.social.nlp_tools import analyze_reddit_text
from app.social.reddit.tools import get_reddit_discussion

load_dotenv()


SOCIAL_SYSTEM = (
    "You are the Social Agent (retail sentiment specialist). You work only for the CIO / upstream "
    "orchestrator and MUST NOT converse with end users.\n"
    "Your job: fetch the last-24h Reddit retail discussion for the given asset, analyze sentiment "
    "and keywords, and persist a JSON report.\n\n"
    "You MUST use tools in this order:\n"
    "1) get_reddit_discussion to fetch the cleaned discussion text.\n"
    "2) analyze_reddit_text to produce a STRICT JSON object with keys: sentiment, keywords, summary.\n"
    "3) build_social_report to merge nlp_result with ingestion meta into a final report object.\n"
    "4) save_social_report to persist the report and obtain report_path.\n\n"
    "Final output MUST be ONLY a single JSON object (no extra text). It must contain at least:\n"
    "- asset\n"
    "- sentiment\n"
    "- keywords\n"
    "- summary\n"
    "- meta\n"
    "- report_path\n"
)


SOCIAL_TOOLS: Sequence[BaseTool] = [
    get_reddit_discussion,
    analyze_reddit_text,
    build_social_report,
    save_social_report,
]


def _should_continue(state: MessagesState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return END
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None)
    if tool_calls:
        return "tools"
    return END


def _make_llm() -> Runnable:
    # Delegate to the same MiniMax env variables configured in app/graph_multi.py
    # (implementation kept local to avoid cross-module coupling).
    from app.social.nlp_tools import _make_minimax_llm  # noqa: WPS433 (local import by intent)

    return _make_minimax_llm().bind_tools(list(SOCIAL_TOOLS))


def build_social_graph():
    """Build the compiled Social Agent graph (ReAct loop with ToolNode)."""

    llm = _make_llm()
    tool_node = ToolNode(list(SOCIAL_TOOLS))

    def agent_node(
        state: MessagesState, *, config: Optional[RunnableConfig] = None
    ) -> MessagesState:
        messages = state.get("messages", [])
        response = llm.invoke(messages, config=config)
        return {"messages": messages + [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def run_social_messages(
    asset: str, *, config: Optional[RunnableConfig] = None
) -> List[BaseMessage]:
    """Run the Social Agent graph and return full message history.

    Args:
        asset: Asset symbol (e.g., BTC, NVDA).
        config: Optional runnable config for tracing/timeouts.

    Returns:
        Message list including tool messages and final AI message.
    """

    compiled = build_social_graph()
    initial: MessagesState = {
        "messages": [
            SystemMessage(content=SOCIAL_SYSTEM),
            HumanMessage(
                content=(
                    f"Generate a Reddit retail sentiment report for asset {asset.strip().upper()} "
                    "using the available tools."
                )
            ),
        ],
    }
    out_state = compiled.invoke(initial, config=config)
    return cast(List[BaseMessage], out_state.get("messages", []))


def run_social_once(asset: str, *, config: Optional[RunnableConfig] = None) -> str:
    """Run Social Agent and return final AI text (expected to be JSON)."""

    messages = run_social_messages(asset, config=config)
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not (getattr(m, "tool_calls", None)):
            content = getattr(m, "content", None)
            if content:
                return str(content)
    return ""


def parse_social_final_json(text: str) -> dict:
    """Parse the final Social Agent output into a Python dict."""

    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty Social Agent final output.")
    return cast(dict, json.loads(raw))
