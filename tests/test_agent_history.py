"""Tests for agent history database operations."""

import sqlite3
from pathlib import Path
import pytest
import json
import uuid
from datetime import datetime, timezone, timedelta
from app.database.agent_history import (
    init_db,
    get_connection,
    save_analysis_run,
    save_agent_execution,
    save_tool_call
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
        'idx_runs_asset',
        'idx_runs_timestamp',
        'idx_exec_run',
        'idx_exec_agent',
        'idx_tool_exec',
        'idx_tool_name',
        'idx_tool_status'
    }

    assert expected_indexes.issubset(indexes)
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
        db_path=str(db_path)
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
        db_path=str(db_path)
    )

    # Then save execution
    execution_id = str(uuid.uuid4())
    agent_type = "quant"
    messages = [
        {"role": "system", "content": "You are an analyst"},
        {"role": "user", "content": "Analyze AAPL"}
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
        db_path=str(db_path)
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
        db_path=str(db_path)
    )
    save_agent_execution(
        execution_id=execution_id,
        run_id=run_id,
        agent_type="quant",
        messages=[],
        start_time=datetime.now(timezone(timedelta(hours=8))),
        db_path=str(db_path)
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
        db_path=str(db_path)
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
