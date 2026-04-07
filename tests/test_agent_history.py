"""Tests for agent history database operations."""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.database.agent_history as agent_history
from app.database.agent_history import (
    get_connection,
    init_db,
    query_agent_messages,
    query_analysis_runs,
    query_run_detail,
    query_tool_calls,
    save_agent_execution,
    save_analysis_run,
    save_tool_call,
)


def test_init_db_creates_tables(tmp_path):
    """Test that init_db creates all required tables."""
    db_path = tmp_path / "test_agent_history.db"
    init_db(str(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check analysis_runs table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_runs'")
    assert cursor.fetchone() is not None

    # Check agent_executions table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_executions'")
    assert cursor.fetchone() is not None

    # Check tool_calls table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tool_calls'")
    assert cursor.fetchone() is not None

    # Check decision_outcomes table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='decision_outcomes'")
    assert cursor.fetchone() is not None

    # Check analysis_progress_events table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_progress_events'"
    )
    assert cursor.fetchone() is not None

    # Check analysis_private_reasoning table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_private_reasoning'"
    )
    assert cursor.fetchone() is not None

    conn.close()


def test_init_db_creates_indexes(tmp_path):
    """Test that init_db creates all required indexes."""
    db_path = tmp_path / "test_agent_history.db"
    init_db(str(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check indexes exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cursor.fetchall()}

    expected_indexes = {
        "idx_runs_asset",
        "idx_runs_timestamp",
        "idx_exec_run",
        "idx_exec_agent",
        "idx_tool_exec",
        "idx_tool_name",
        "idx_tool_status",
        "idx_progress_run_sequence",
        "idx_reasoning_run_stage",
    }

    assert expected_indexes.issubset(indexes)
    conn.close()


def test_save_analysis_progress_event_round_trips_json_payload(tmp_path: Path) -> None:
    """Progress events should persist sanitized payloads for a run."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    save_event = getattr(agent_history, "save_analysis_progress_event", None)
    assert callable(save_event)

    run_id = "20260321_143052"
    save_analysis_run(
        run_id=run_id,
        asset="AAPL",
        query="test",
        timestamp=datetime.now(timezone(timedelta(hours=8))),
        db_path=str(db_path),
    )

    save_event(
        event_id="evt_000001",
        run_id=run_id,
        sequence=1,
        stage="news",
        event_type="tool_result",
        status="completed",
        message="Fetched 8 news articles from Tavily",
        timestamp=datetime.now(timezone.utc),
        data={"tool": "search_realtime_news", "provider": "tavily", "article_count": 8},
        db_path=str(db_path),
    )

    conn = get_connection(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT event_id, run_id, sequence, stage, event_type, status, message, data_json
        FROM analysis_progress_events
        WHERE event_id = ?
        """,
        ("evt_000001",),
    )
    row = cursor.fetchone()
    assert row is not None
    assert row["run_id"] == run_id
    assert row["sequence"] == 1
    assert row["stage"] == "news"
    assert row["event_type"] == "tool_result"
    assert row["status"] == "completed"
    payload = json.loads(row["data_json"])
    assert payload["provider"] == "tavily"
    assert payload["article_count"] == 8
    conn.close()


def test_save_private_reasoning_persists_versioned_payload(tmp_path: Path) -> None:
    """Private reasoning should be stored as versioned JSON envelopes."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    save_reasoning = getattr(agent_history, "save_private_reasoning", None)
    assert callable(save_reasoning)

    run_id = "20260321_143052"
    save_analysis_run(
        run_id=run_id,
        asset="AAPL",
        query="test",
        timestamp=datetime.now(timezone(timedelta(hours=8))),
        db_path=str(db_path),
    )

    save_reasoning(
        reasoning_id="rsn_000001",
        run_id=run_id,
        stage="cio",
        agent_type="cio",
        payload={
            "schema_version": 1,
            "reasoning_kind": "cio_synthesis",
            "prompt": "Summarize all reports",
            "raw_completion": "Bullish with caveats",
            "parsed_summary": {"decision": "bullish"},
            "tool_context": {"quant_available": True},
        },
        created_at=datetime.now(timezone.utc),
        db_path=str(db_path),
    )

    conn = get_connection(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT reasoning_id, run_id, stage, agent_type, payload_json
        FROM analysis_private_reasoning
        WHERE reasoning_id = ?
        """,
        ("rsn_000001",),
    )
    row = cursor.fetchone()
    assert row is not None
    assert row["run_id"] == run_id
    assert row["stage"] == "cio"
    payload = json.loads(row["payload_json"])
    assert payload["schema_version"] == 1
    assert payload["reasoning_kind"] == "cio_synthesis"
    assert payload["parsed_summary"]["decision"] == "bullish"
    conn.close()


def test_save_analysis_run(tmp_path):
    """Test saving an analysis run."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    run_id = "20260321_143052"
    asset = "AAPL"
    query = "分析AAPL的最新股价"
    timestamp = datetime.now(timezone(timedelta(hours=8)))
    final_decision = "综合技术面和新闻面，建议持有"

    save_analysis_run(
        run_id=run_id,
        asset=asset,
        query=query,
        timestamp=timestamp,
        final_decision=final_decision,
        db_path=str(db_path),
    )

    conn = get_connection(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()

    assert row is not None
    assert row["run_id"] == run_id
    assert row["asset"] == asset
    assert row["query"] == query
    assert row["final_decision"] == final_decision
    conn.close()


def test_save_agent_execution(tmp_path):
    """Test saving an agent execution."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    # First create a run
    run_id = "20260321_143052"
    save_analysis_run(
        run_id=run_id,
        asset="AAPL",
        query="test",
        timestamp=datetime.now(timezone(timedelta(hours=8))),
        db_path=str(db_path),
    )

    # Then save execution
    execution_id = str(uuid.uuid4())
    agent_type = "quant"
    messages = [
        {"role": "system", "content": "You are an analyst"},
        {"role": "user", "content": "Analyze AAPL"},
    ]
    output_text = "Technical analysis shows..."
    start_time = datetime.now(timezone(timedelta(hours=8)))
    end_time = start_time + timedelta(seconds=23.5)

    save_agent_execution(
        execution_id=execution_id,
        run_id=run_id,
        agent_type=agent_type,
        messages=messages,
        output_text=output_text,
        start_time=start_time,
        end_time=end_time,
        db_path=str(db_path),
    )

    conn = get_connection(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent_executions WHERE execution_id = ?", (execution_id,))
    row = cursor.fetchone()

    assert row is not None
    assert row["execution_id"] == execution_id
    assert row["run_id"] == run_id
    assert row["agent_type"] == agent_type
    assert row["output_text"] == output_text
    assert row["duration_seconds"] == pytest.approx(23.5, rel=0.1)

    # Verify messages_json
    stored_messages = json.loads(row["messages_json"])
    assert len(stored_messages) == 2
    assert stored_messages[0]["role"] == "system"
    conn.close()


def test_save_tool_call(tmp_path):
    """Test saving a tool call."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    # Setup: create run and execution
    run_id = "20260321_143052"
    execution_id = str(uuid.uuid4())
    save_analysis_run(
        run_id=run_id,
        asset="AAPL",
        query="test",
        timestamp=datetime.now(timezone(timedelta(hours=8))),
        db_path=str(db_path),
    )
    save_agent_execution(
        execution_id=execution_id,
        run_id=run_id,
        agent_type="quant",
        messages=[],
        start_time=datetime.now(timezone(timedelta(hours=8))),
        db_path=str(db_path),
    )

    # Save tool call
    call_id = str(uuid.uuid4())
    tool_name = "get_stock_data"
    arguments = {"ticker": "AAPL", "period": "3mo"}
    result = {"data": [{"close": 150.0}]}
    status = "success"
    timestamp = datetime.now(timezone(timedelta(hours=8)))

    save_tool_call(
        call_id=call_id,
        execution_id=execution_id,
        tool_name=tool_name,
        arguments=arguments,
        result=result,
        status=status,
        timestamp=timestamp,
        db_path=str(db_path),
    )

    conn = get_connection(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tool_calls WHERE call_id = ?", (call_id,))
    row = cursor.fetchone()

    assert row is not None
    assert row["call_id"] == call_id
    assert row["execution_id"] == execution_id
    assert row["tool_name"] == tool_name
    assert row["status"] == status
    assert row["error_message"] is None

    # Verify JSON fields
    stored_args = json.loads(row["arguments_json"])
    assert stored_args["ticker"] == "AAPL"
    stored_result = json.loads(row["result_json"])
    assert stored_result["data"][0]["close"] == 150.0
    conn.close()


def test_query_analysis_runs(tmp_path):
    """Test querying analysis runs with filters."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    # Insert test data
    tz = timezone(timedelta(hours=8))
    save_analysis_run(
        "20260321_100000",
        "AAPL",
        "test1",
        datetime(2026, 3, 21, 10, 0, 0, tzinfo=tz),
        db_path=str(db_path),
    )
    save_analysis_run(
        "20260321_110000",
        "AAPL",
        "test2",
        datetime(2026, 3, 21, 11, 0, 0, tzinfo=tz),
        db_path=str(db_path),
    )
    save_analysis_run(
        "20260321_120000",
        "NVDA",
        "test3",
        datetime(2026, 3, 21, 12, 0, 0, tzinfo=tz),
        db_path=str(db_path),
    )

    # Query all
    results = query_analysis_runs(db_path=str(db_path))
    assert len(results) == 3

    # Query by asset
    results = query_analysis_runs(asset="AAPL", db_path=str(db_path))
    assert len(results) == 2
    assert all(r["asset"] == "AAPL" for r in results)

    # Query with limit
    results = query_analysis_runs(limit=1, db_path=str(db_path))
    assert len(results) == 1


def test_query_run_detail(tmp_path):
    """Test querying detailed run information."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    # Setup test data
    run_id = "20260321_143052"
    tz = timezone(timedelta(hours=8))
    save_analysis_run(run_id, "AAPL", "test", datetime.now(tz), "decision", str(db_path))

    exec_id = str(uuid.uuid4())
    save_agent_execution(
        exec_id,
        run_id,
        "quant",
        [{"role": "system", "content": "test"}],
        datetime.now(tz),
        "output",
        datetime.now(tz),
        str(db_path),
    )

    # Query detail
    result = query_run_detail(run_id, db_path=str(db_path))

    assert result is not None
    assert result["run_id"] == run_id
    assert result["asset"] == "AAPL"
    assert "agents" in result
    assert len(result["agents"]) == 1
    assert result["agents"][0]["agent_type"] == "quant"


def test_query_agent_messages(tmp_path):
    """Test querying agent messages."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    # Setup
    run_id = "20260321_143052"
    exec_id = str(uuid.uuid4())
    tz = timezone(timedelta(hours=8))
    messages = [
        {"role": "system", "content": "You are an analyst"},
        {"role": "user", "content": "Analyze AAPL"},
    ]

    save_analysis_run(run_id, "AAPL", "test", datetime.now(tz), db_path=str(db_path))
    save_agent_execution(exec_id, run_id, "quant", messages, datetime.now(tz), db_path=str(db_path))

    # Query messages
    result = query_agent_messages(exec_id, db_path=str(db_path))

    assert result is not None
    assert result["execution_id"] == exec_id
    assert result["agent_type"] == "quant"
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "system"


def test_query_tool_calls(tmp_path):
    """Test querying tool calls with filters."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    # Setup
    run_id = "20260321_143052"
    exec_id = str(uuid.uuid4())
    tz = timezone(timedelta(hours=8))

    save_analysis_run(run_id, "AAPL", "test", datetime.now(tz), db_path=str(db_path))
    save_agent_execution(exec_id, run_id, "quant", [], datetime.now(tz), db_path=str(db_path))

    # Insert tool calls
    save_tool_call(
        str(uuid.uuid4()),
        exec_id,
        "get_stock_data",
        {"ticker": "AAPL"},
        "success",
        datetime.now(tz),
        {"data": []},
        db_path=str(db_path),
    )
    save_tool_call(
        str(uuid.uuid4()),
        exec_id,
        "search_news",
        {"query": "AAPL"},
        "failed",
        datetime.now(tz),
        error_message="timeout",
        db_path=str(db_path),
    )

    # Query all
    results = query_tool_calls(db_path=str(db_path))
    assert len(results) == 2

    # Query by tool_name
    results = query_tool_calls(tool_name="get_stock_data", db_path=str(db_path))
    assert len(results) == 1
    assert results[0]["tool_name"] == "get_stock_data"

    # Query by status
    results = query_tool_calls(status="failed", db_path=str(db_path))
    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert results[0]["error_message"] == "timeout"
