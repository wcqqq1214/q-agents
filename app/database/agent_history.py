"""Agent decision history database operations."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    # Create analysis_progress_events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_progress_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            stage TEXT NOT NULL,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            data_json TEXT,
            timestamp DATETIME NOT NULL,
            FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
        )
    """)

    # Create indexes for analysis_progress_events
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_progress_run_sequence
        ON analysis_progress_events(run_id, sequence)
        """
    )

    # Create analysis_private_reasoning table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_private_reasoning (
            reasoning_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
        )
    """)

    # Create indexes for analysis_private_reasoning
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reasoning_run_stage
        ON analysis_private_reasoning(run_id, stage)
        """
    )

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
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Save an analysis run to the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO analysis_runs (run_id, asset, query, timestamp, final_decision)
        VALUES (?, ?, ?, ?, ?)
    """,
        (run_id, asset, query, timestamp.isoformat(), final_decision),
    )

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
    db_path: str = DEFAULT_DB_PATH,
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

    cursor.execute(
        """
        INSERT INTO agent_executions
        (execution_id, run_id, agent_type, messages_json, output_text, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            execution_id,
            run_id,
            agent_type,
            messages_json,
            output_text,
            start_time.isoformat(),
            end_time.isoformat() if end_time else None,
            duration_seconds,
        ),
    )

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
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Save a tool call to the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Serialize JSON fields
    arguments_json = json.dumps(arguments, ensure_ascii=False)
    result_json = json.dumps(result, ensure_ascii=False) if result else None

    cursor.execute(
        """
        INSERT INTO tool_calls
        (call_id, execution_id, tool_name, arguments_json, result_json, status, error_message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            call_id,
            execution_id,
            tool_name,
            arguments_json,
            result_json,
            status,
            error_message,
            timestamp.isoformat(),
        ),
    )

    conn.commit()
    conn.close()


def save_analysis_progress_event(
    event_id: str,
    run_id: str,
    sequence: int,
    stage: str,
    event_type: str,
    status: str,
    message: str,
    timestamp: datetime,
    data: Optional[Dict[str, Any]] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Save a normalized public progress event to the history database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    data_json = json.dumps(data, ensure_ascii=False) if data is not None else None

    cursor.execute(
        """
        INSERT INTO analysis_progress_events
        (event_id, run_id, sequence, stage, event_type, status, message, data_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            run_id,
            sequence,
            stage,
            event_type,
            status,
            message,
            data_json,
            timestamp.isoformat(),
        ),
    )

    conn.commit()
    conn.close()


def save_private_reasoning(
    reasoning_id: str,
    run_id: str,
    stage: str,
    agent_type: str,
    payload: Dict[str, Any],
    created_at: datetime,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Save a private LLM reasoning payload for internal-only use."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    payload_json = json.dumps(payload, ensure_ascii=False)

    cursor.execute(
        """
        INSERT INTO analysis_private_reasoning
        (reasoning_id, run_id, stage, agent_type, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            reasoning_id,
            run_id,
            stage,
            agent_type,
            payload_json,
            created_at.isoformat(),
        ),
    )

    conn.commit()
    conn.close()


def query_analysis_runs(
    asset: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Query analysis runs with optional filters.

    Args:
        asset: Filter by asset ticker
        date_from: Filter by start date (ISO format)
        date_to: Filter by end date (ISO format)
        limit: Maximum number of results
        offset: Offset for pagination
        db_path: Database file path

    Returns:
        List of analysis run dicts
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM analysis_runs WHERE 1=1"
    params = []

    if asset:
        query += " AND asset = ?"
        params.append(asset)
    if date_from:
        query += " AND timestamp >= ?"
        params.append(date_from)
    if date_to:
        query += " AND timestamp <= ?"
        params.append(date_to)

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def query_run_detail(run_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Query detailed information for a single run.

    Returns:
        Dict with run info and list of agent executions, or None if not found
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Get run info
    cursor.execute("SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,))
    run_row = cursor.fetchone()

    if not run_row:
        conn.close()
        return None

    run_dict = dict(run_row)

    # Get agent executions
    cursor.execute(
        """
        SELECT execution_id, agent_type, output_text, start_time, end_time, duration_seconds
        FROM agent_executions
        WHERE run_id = ?
        ORDER BY start_time
    """,
        (run_id,),
    )

    agent_rows = cursor.fetchall()
    run_dict["agents"] = [dict(row) for row in agent_rows]

    conn.close()
    return run_dict


def query_agent_messages(
    execution_id: str, db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """Query complete message history for an agent execution.

    Returns:
        Dict with execution info and messages list, or None if not found
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT execution_id, agent_type, messages_json
        FROM agent_executions
        WHERE execution_id = ?
    """,
        (execution_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    result = {
        "execution_id": row["execution_id"],
        "agent_type": row["agent_type"],
        "messages": json.loads(row["messages_json"]),
    }

    return result


def query_tool_calls(
    tool_name: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Query tool calls with optional filters.

    Args:
        tool_name: Filter by tool name
        status: Filter by status ('success' or 'failed')
        date_from: Filter by start date (ISO format)
        limit: Maximum number of results
        offset: Offset for pagination
        db_path: Database file path

    Returns:
        List of tool call dicts
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM tool_calls WHERE 1=1"
    params = []

    if tool_name:
        query += " AND tool_name = ?"
        params.append(tool_name)
    if status:
        query += " AND status = ?"
        params.append(status)
    if date_from:
        query += " AND timestamp >= ?"
        params.append(date_from)

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_analysis_run_decision(
    run_id: str, final_decision: str, db_path: str = DEFAULT_DB_PATH
) -> None:
    """Update the final_decision field for an analysis run."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE analysis_runs
        SET final_decision = ?
        WHERE run_id = ?
    """,
        (final_decision, run_id),
    )

    conn.commit()
    conn.close()
