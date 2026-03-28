"""Tests for history API endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

from app.database.agent_history import init_db, save_agent_execution, save_analysis_run


def test_get_analysis_runs(tmp_path, monkeypatch):
    """Test GET /api/analysis-runs endpoint."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    monkeypatch.setenv("AGENT_HISTORY_DB_PATH", str(db_path))

    # Create client AFTER setting environment variable
    from fastapi.testclient import TestClient

    from app.api.main import app

    client = TestClient(app)

    # Insert test data
    tz = timezone(timedelta(hours=8))
    save_analysis_run(
        "20260321_100000",
        "AAPL",
        "test query",
        datetime.now(tz),
        "decision",
        str(db_path),
    )

    response = client.get("/api/analysis-runs")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert len(data["items"]) >= 1


def test_get_analysis_runs_with_filters(tmp_path, monkeypatch):
    """Test GET /api/analysis-runs with filters."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    monkeypatch.setenv("AGENT_HISTORY_DB_PATH", str(db_path))

    from fastapi.testclient import TestClient

    from app.api.main import app

    client = TestClient(app)

    tz = timezone(timedelta(hours=8))
    save_analysis_run("20260321_100000", "AAPL", "test1", datetime.now(tz), db_path=str(db_path))
    save_analysis_run("20260321_110000", "NVDA", "test2", datetime.now(tz), db_path=str(db_path))

    response = client.get("/api/analysis-runs?asset=AAPL")
    assert response.status_code == 200
    data = response.json()
    assert all(item["asset"] == "AAPL" for item in data["items"])


def test_get_run_detail(tmp_path, monkeypatch):
    """Test GET /api/analysis-runs/{run_id} endpoint."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    monkeypatch.setenv("AGENT_HISTORY_DB_PATH", str(db_path))

    from fastapi.testclient import TestClient

    from app.api.main import app

    client = TestClient(app)

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
        db_path=str(db_path),
    )

    response = client.get(f"/api/analysis-runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert "agents" in data
    assert len(data["agents"]) == 1


def test_get_run_detail_not_found(tmp_path, monkeypatch):
    """Test GET /api/analysis-runs/{run_id} with non-existent ID."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    monkeypatch.setenv("AGENT_HISTORY_DB_PATH", str(db_path))

    from fastapi.testclient import TestClient

    from app.api.main import app

    client = TestClient(app)

    response = client.get("/api/analysis-runs/nonexistent")
    assert response.status_code == 404
