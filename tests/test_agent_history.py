"""Tests for agent history database operations."""

import sqlite3
from pathlib import Path
import pytest
from app.database.agent_history import init_db, get_connection


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
