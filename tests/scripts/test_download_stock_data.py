"""Tests for the historical stock download script."""

import importlib
from datetime import date

from app.database.schema import get_conn, init_db


def test_detect_gaps_skips_nyse_holidays(monkeypatch, tmp_path):
    module = importlib.import_module("scripts.data.download_stock_data")
    db_path = tmp_path / "finance_data.db"

    init_db(db_path)
    conn = get_conn(db_path)
    conn.executemany(
        """
        INSERT INTO ohlc (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAPL", "2025-07-01", 1.0, 1.0, 1.0, 1.0, 1),
            ("AAPL", "2025-07-02", 1.0, 1.0, 1.0, 1.0, 1),
            ("AAPL", "2025-07-07", 1.0, 1.0, 1.0, 1.0, 1),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(module, "get_conn", lambda: get_conn(db_path))

    gaps = module.detect_gaps("AAPL", date(2025, 7, 1), date(2025, 7, 7))

    assert gaps == [(date(2025, 7, 3), date(2025, 7, 3))]


def test_to_yfinance_end_date_converts_to_exclusive_boundary():
    module = importlib.import_module("scripts.data.download_stock_data")

    assert module._to_yfinance_end_date(date(2025, 7, 3)) == "2025-07-04"
