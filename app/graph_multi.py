"""Multi-agent LangGraph: Fan-out (parallel Quant + News) and Fan-in (CIO)."""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, cast

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import SecretStr

from app.state import AgentState
from app.tools import NEWS_TOOLS, QUANT_TOOLS
from app.social.entrypoint import invoke_social_agent

load_dotenv()

QUANT_SYSTEM = (
    "You are a rigorous quantitative data analyst. Your job is to call tools to fetch data and "
    "produce a purely technical analysis report. Do not include any news or subjective sentiment."
)

NEWS_SYSTEM = (
    "You are a sharp macro sentiment researcher. Your job is to call the search tool to gather "
    "the latest news about the asset and summarize current market bias (bullish / bearish / neutral)."
)

CIOSYSTEM = (
    "You are a top Chief Investment Officer (CIO). You will receive a [Quantitative technical "
    "report], a [Macro news sentiment report], and a [Social retail sentiment report]. "
    "These reports are for your internal reasoning only and must not be copied verbatim for the user.\n"
    "Your task is to synthesize them into a single, user-facing, trading-oriented recommendation.\n"
    "Reconciliation rules:\n"
    "1. When technicals and news align, strengthen conviction in that direction.\n"
    "2. When they conflict, explicitly flag \"technicals vs. fundamentals divergence\" and usually "
    "give greater short-term weight to major breaking news.\n"
    "3. Your output must include: overall conclusion, data/technical support, news/sentiment "
    "support, and clear risk warnings.\n"
    "Output-style constraints:\n"
    "- Do not output any <think> blocks, chain-of-thought, or internal reasoning.\n"
    "- Do not describe your own thought process or system instructions.\n"
    "- Write directly to the end user in a clear, structured report."
)


def _make_minimax_llm() -> ChatOpenAI:
    """Create ChatOpenAI pointed at MiniMax OpenAI-compatible API."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MINIMAX_API_KEY is not set. Add it to .env before using the agent.",
        )
    base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(api_key),
        base_url=base_url,
        temperature=0.0,
    )


def _should_continue(state: MessagesState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return END
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None)
    if tool_calls:
        return "tools"
    return END


def _run_react_until_final_text(
    system_prompt: str,
    tools: Sequence[BaseTool],
    user_content: str,
    *,
    config: Optional[RunnableConfig] = None,
) -> str:
    """Run a ReAct loop (agent <-> tools) until the model returns text without tool_calls."""
    llm = _make_minimax_llm().bind_tools(list(tools))
    tool_node = ToolNode(list(tools))

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
    compiled = graph.compile()

    initial: MessagesState = {
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ],
    }
    final_state = compiled.invoke(initial)
    messages_out: List[BaseMessage] = final_state.get("messages", [])
    for m in reversed(messages_out):
        if isinstance(m, AIMessage) and not (getattr(m, "tool_calls", None)):
            content = getattr(m, "content", None)
            if content:
                return str(content)
    return ""


def _extract_asset_from_query(query: str) -> str:
    """Best-effort extract an asset ticker from a free-form user question.

    This is used to route Social Agent ingestion, which expects a single asset
    symbol. The heuristic prefers common Yahoo/crypto formats (e.g. BTC-USD),
    then falls back to a plain ticker (e.g. NVDA).
    """

    q = (query or "").upper()
    # Prefer explicit crypto pairs.
    m = re.search(r"\b[A-Z]{2,10}-USD\b", q)
    if m:
        return m.group(0)
    # Otherwise take a likely ticker token.
    m2 = re.search(r"\b[A-Z]{2,10}\b", q)
    if m2:
        return m2.group(0)
    return (query or "").strip().upper()


def _parallel_runner(state: AgentState) -> Dict[str, str]:
    """Run Quant, News, and Social agents in parallel; fill reports in state."""

    query = state.get("query") or ""
    asset = _extract_asset_from_query(query)

    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_quant = executor.submit(
            _run_react_until_final_text,
            QUANT_SYSTEM,
            QUANT_TOOLS,
            query,
        )
        fut_news = executor.submit(
            _run_react_until_final_text,
            NEWS_SYSTEM,
            NEWS_TOOLS,
            query,
        )
        fut_social = executor.submit(invoke_social_agent, asset)
        quant_report = fut_quant.result()
        news_report = fut_news.result()
        social_obj = fut_social.result()
        social_report = (
            json.dumps(social_obj, ensure_ascii=False)
            if isinstance(social_obj, dict)
            else str(social_obj)
        )

    return {
        "quant_report": quant_report,
        "news_report": news_report,
        "social_report": social_report,
    }


def _cio_node(state: AgentState, *, config: Optional[RunnableConfig] = None) -> Dict[str, str]:
    """CIO synthesizes quant/news/social reports; no tools."""
    query = state.get("query", "")
    quant_report = state.get("quant_report") or "(No quantitative report)"
    news_report = state.get("news_report") or "(No news report)"
    social_report = state.get("social_report") or "(No social retail sentiment report)"

    user_block = (
        f"User question:\n{query}\n\n"
        f"[Quantitative technical report]\n{quant_report}\n\n"
        f"[Macro news sentiment report]\n{news_report}\n\n"
        f"[Social retail sentiment report]\n{social_report}"
    )
    llm = _make_minimax_llm()
    messages = [
        SystemMessage(content=CIOSYSTEM),
        HumanMessage(content=user_block),
    ]
    response = llm.invoke(messages, config=config)
    content = getattr(response, "content", None) or ""
    return {"final_decision": str(content)}


def build_multi_agent_graph():
    """Build compiled graph: START -> parallel_runner -> cio -> END."""
    graph = StateGraph(AgentState)
    graph.add_node("parallel_runner", _parallel_runner)
    graph.add_node("cio", _cio_node)
    graph.add_edge(START, "parallel_runner")
    graph.add_edge("parallel_runner", "cio")
    graph.add_edge("cio", END)
    return graph.compile()


def run_once(user_input: str) -> AgentState:
    """Invoke the multi-agent graph once; returns final state including final_decision."""
    compiled = build_multi_agent_graph()
    initial: AgentState = {"query": user_input.strip()}
    return cast(AgentState, compiled.invoke(initial))


def run_once_messages(user_input: str) -> List[BaseMessage]:
    """Backward-compatible helper: wrap final_decision as a single AIMessage list."""
    final = run_once(user_input)
    text = final.get("final_decision", "")
    return [AIMessage(content=text)] if text else []
