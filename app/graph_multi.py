"""Multi-agent LangGraph: Fan-out (parallel Quant + News) and Fan-in (CIO)."""

from __future__ import annotations

import json
import os
import re
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, cast

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.llm_config import create_llm
from app.state import AgentState
from app.tools import NEWS_TOOLS, QUANT_TOOLS
from app.news.generate_report import generate_report as generate_news_report
from app.quant.generate_report import generate_report as generate_quant_report
from app.reporting.run_context import make_run_dir
from app.reporting.writer import write_json
from app.social.generate_report import generate_report as generate_social_report
from app.database.agent_history import save_agent_execution, save_tool_call, save_analysis_run, update_analysis_run_decision, init_db
from app.database.message_adapter import convert_messages_to_standard

load_dotenv()

logger = logging.getLogger(__name__)

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
    "Language rule:\n"
    "- Always answer in the SAME language as the user's question. If the question is in Chinese, your full answer must be in Chinese. "
    "If the question is in English, answer fully in English.\n"
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
    run_id: Optional[str] = None,
    agent_type: Optional[str] = None,
) -> str:
    """Run a ReAct loop (agent <-> tools) until the model returns text without tool_calls."""
    llm = create_llm().bind_tools(list(tools))
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

    # Record start time
    start_time = datetime.now(timezone(timedelta(hours=8)))

    final_state = compiled.invoke(initial)
    messages_out: List[BaseMessage] = final_state.get("messages", [])

    # Extract final output
    output_text = ""
    for m in reversed(messages_out):
        if isinstance(m, AIMessage) and not (getattr(m, "tool_calls", None)):
            content = getattr(m, "content", None)
            if content:
                output_text = str(content)
                break

    # Record to database if run_id and agent_type provided
    if run_id and agent_type:
        try:
            end_time = datetime.now(timezone(timedelta(hours=8)))
            execution_id = str(uuid.uuid4())

            # Convert messages to standard format
            standard_messages = convert_messages_to_standard(messages_out)

            # Save agent execution
            db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")
            init_db(db_path)  # Ensure DB exists

            save_agent_execution(
                execution_id=execution_id,
                run_id=run_id,
                agent_type=agent_type,
                messages=standard_messages,
                output_text=output_text,
                start_time=start_time,
                end_time=end_time,
                db_path=db_path
            )

            # Extract and save tool calls
            for msg in messages_out:
                if isinstance(msg, AIMessage):
                    tool_calls = getattr(msg, "tool_calls", None)
                    if tool_calls:
                        for tc in tool_calls:
                            call_id = tc.get("id", str(uuid.uuid4()))
                            tool_name = tc.get("name", "")
                            arguments = tc.get("args", {})

                            # Find corresponding tool result
                            tool_result = None
                            for next_msg in messages_out[messages_out.index(msg)+1:]:
                                if isinstance(next_msg, ToolMessage) and next_msg.tool_call_id == call_id:
                                    try:
                                        tool_result = json.loads(next_msg.content)
                                    except:
                                        tool_result = {"raw": next_msg.content}
                                    break

                            save_tool_call(
                                call_id=call_id,
                                execution_id=execution_id,
                                tool_name=tool_name,
                                arguments=arguments,
                                result=tool_result,
                                status="success" if tool_result else "unknown",
                                timestamp=start_time,
                                db_path=db_path
                            )
        except Exception as e:
            # Log error but don't fail the agent execution
            logger.error(f"Failed to record agent execution to history database: {e}", exc_info=True)

    return output_text


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

    tokens = re.findall(r"\b[A-Z]{2,10}\b", q)
    if not tokens:
        return (query or "").strip().upper()

    stop = {
        "PLEASE",
        "ANALYZE",
        "ANALYSIS",
        "WITH",
        "AND",
        "GIVE",
        "A",
        "TRADING",
        "RECOMMENDATION",
        "NEWS",
        "SOCIAL",
        "QUANT",
    }
    crypto = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK"}

    for t in tokens:
        if t in crypto:
            return t

    candidates = [t for t in tokens if t not in stop]
    if candidates:
        # Prefer the last candidate (often "analyze X" style queries).
        return candidates[-1]
    return tokens[-1]


def _parallel_runner(state: AgentState) -> Dict[str, Any]:
    """Run Quant, News, and Social agents in parallel; fill reports in state."""

    query = state.get("query") or ""
    asset = _extract_asset_from_query(query)
    ctx = make_run_dir(asset)

    # Save analysis run to database
    try:
        db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")
        init_db(db_path)
        save_analysis_run(
            run_id=ctx.run_id,
            asset=asset,
            query=query,
            timestamp=datetime.now(timezone(timedelta(hours=8))),
            db_path=db_path
        )
    except Exception as e:
        logger.error(f"Failed to save analysis run to history database: {e}", exc_info=True)

    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_quant = executor.submit(
            generate_quant_report,
            ctx.asset,
            str(ctx.run_dir),
        )
        fut_news = executor.submit(
            generate_news_report,
            ctx.asset,
            str(ctx.run_dir),
        )
        fut_social = executor.submit(generate_social_report, ctx.asset, str(ctx.run_dir))
        quant_obj = cast(Dict[str, Any], fut_quant.result())
        news_obj = cast(Dict[str, Any], fut_news.result())
        social_obj = cast(Dict[str, Any], fut_social.result())

        quant_report = json.dumps(quant_obj, ensure_ascii=False)
        news_report = json.dumps(news_obj, ensure_ascii=False)
        social_report = json.dumps(social_obj, ensure_ascii=False)

    out: Dict[str, Any] = {
        "run_id": ctx.run_id,
        "run_dir": str(ctx.run_dir),
        "quant_report": quant_report,
        "news_report": news_report,
        "social_report": social_report,
        "quant_report_obj": quant_obj,
        "news_report_obj": news_obj,
        "social_report_obj": social_obj,
        "quant_report_path": str(Path(ctx.run_dir) / "quant.json"),
        "news_report_path": str(Path(ctx.run_dir) / "news.json"),
        "social_report_path": str(Path(ctx.run_dir) / "social.json"),
    }
    return out


def _cio_node(state: AgentState, *, config: Optional[RunnableConfig] = None) -> Dict[str, str]:
    """CIO synthesizes quant/news/social reports; no tools."""
    query = state.get("query", "")
    quant_report = state.get("quant_report") or "(No quantitative report)"
    news_report = state.get("news_report") or "(No news report)"
    social_report = state.get("social_report") or "(No social retail sentiment report)"
    asset = _extract_asset_from_query(query)
    run_id = state.get("run_id")
    run_dir = state.get("run_dir")

    user_block = (
        f"User question:\n{query}\n\n"
        f"[Quantitative technical report]\n{quant_report}\n\n"
        f"[Macro news sentiment report]\n{news_report}\n\n"
        f"[Social retail sentiment report]\n{social_report}"
    )
    llm = create_llm()
    messages = [
        SystemMessage(content=CIOSYSTEM),
        HumanMessage(content=user_block),
    ]
    response = llm.invoke(messages, config=config)
    content = getattr(response, "content", None) or ""

    cio_obj: Dict[str, Any] = {
        "asset": (asset or "").strip().upper(),
        "module": "cio",
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "run_id": run_id,
        },
        "report_paths": {
            "quant": state.get("quant_report_path"),
            "news": state.get("news_report_path"),
            "social": state.get("social_report_path"),
        },
        "final_decision": str(content),
    }

    cio_path = None
    if run_dir:
        cio_path = str(Path(run_dir) / "cio.json")
        write_json(Path(cio_path), cio_obj)
        cio_obj["report_path"] = cio_path

    # Update final_decision in database
    if run_id:
        try:
            db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")
            update_analysis_run_decision(run_id, str(content), db_path)
        except Exception as e:
            logger.error(f"Failed to update final_decision in history database: {e}", exc_info=True)

    return {"final_decision": str(content), "cio_report_path": cio_path or ""}


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
