"""Agent decision history database operations."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Optional, Any, Dict, List
from datetime import datetime

DEFAULT_DB_PATH = "data/agent_history.db"


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Get a connection to the agent history database."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize the agent history database with schema."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Create analysis_runs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            asset TEXT NOT NULL,
            query TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            final_decision TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for analysis_runs
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_asset ON analysis_runs(asset)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON analysis_runs(timestamp)")

    # Create agent_executions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_executions (
            execution_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            messages_json TEXT NOT NULL,
            output_text TEXT,
            start_time DATETIME NOT NULL,
            end_time DATETIME,
            duration_seconds REAL,
            FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
        )
    """)

    # Create indexes for agent_executions
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_run ON agent_executions(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_agent ON agent_executions(agent_type)")

    # Create tool_calls table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            call_id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments_json TEXT NOT NULL,
            result_json TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            timestamp DATETIME NOT NULL,
            FOREIGN KEY (execution_id) REFERENCES agent_executions(execution_id)
        )
    """)

    # Create indexes for tool_calls
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_exec ON tool_calls(execution_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_calls(tool_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_status ON tool_calls(status)")

    # Create decision_outcomes table (reserved for future use)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_outcomes (
            outcome_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            predicted_direction TEXT,
            actual_outcome TEXT,
            evaluation_date DATE,
            notes TEXT,
            FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
        )
    """)

    conn.commit()
    conn.close()


def save_analysis_run(
    run_id: str,
    asset: str,
    query: str,
    timestamp: datetime,
    final_decision: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> None:
    """Save an analysis run to the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO analysis_runs (run_id, asset, query, timestamp, final_decision)
        VALUES (?, ?, ?, ?, ?)
    """, (run_id, asset, query, timestamp.isoformat(), final_decision))

    conn.commit()
    conn.close()


def save_agent_execution(
    execution_id: str,
    run_id: str,
    agent_type: str,
    messages: List[Dict[str, Any]],
    start_time: datetime,
    output_text: Optional[str] = None,
    end_time: Optional[datetime] = None,
    db_path: str = DEFAULT_DB_PATH
) -> None:
    """Save an agent execution to the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Calculate duration if end_time provided
    duration_seconds = None
    if end_time:
        duration_seconds = (end_time - start_time).total_seconds()

    # Serialize messages to JSON
    messages_json = json.dumps(messages, ensure_ascii=False)

    cursor.execute("""
        INSERT INTO agent_executions
        (execution_id, run_id, agent_type, messages_json, output_text, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        execution_id,
        run_id,
        agent_type,
        messages_json,
        output_text,
        start_time.isoformat(),
        end_time.isoformat() if end_time else None,
        duration_seconds
    ))

    conn.commit()
    conn.close()


def save_tool_call(
    call_id: str,
    execution_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    status: str,
    timestamp: datetime,
    result: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> None:
    """Save a tool call to the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Serialize JSON fields
    arguments_json = json.dumps(arguments, ensure_ascii=False)
    result_json = json.dumps(result, ensure_ascii=False) if result else None

    cursor.execute("""
        INSERT INTO tool_calls
        (call_id, execution_id, tool_name, arguments_json, result_json, status, error_message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        call_id,
        execution_id,
        tool_name,
        arguments_json,
        result_json,
        status,
        error_message,
        timestamp.isoformat()
    ))

    conn.commit()
    conn.close()
