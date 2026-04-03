def test_get_reports_returns_stored_asset_type(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from app.api.main import app

    report_dir = tmp_path / "data" / "reports" / "20260403_120000_NVDA"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text(
        json.dumps(
            {
                "symbol": "NVDA",
                "timestamp": "2026-04-03T04:00:00Z",
                "asset_type": "stocks",
                "query": "Analyze NVDA",
                "reports": {"cio": "x", "quant": None, "news": None, "social": None},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.api.routes.reports.REPORTS_DIR", report_dir.parent)
    client = TestClient(app)
    response = client.get("/api/reports")
    assert response.json()[0]["asset_type"] == "stocks"


def test_get_reports_normalizes_legacy_report_without_asset_type_or_reports(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from app.api.main import app

    report_dir = tmp_path / "data" / "reports" / "20260403_120000_BTC"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text(
        json.dumps(
            {
                "symbol": "BTC",
                "timestamp": "2026-04-03T04:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.api.routes.reports.REPORTS_DIR", report_dir.parent)
    client = TestClient(app)
    response = client.get("/api/reports")
    body = response.json()[0]
    assert body["asset_type"] == "crypto"
    assert body["query"] == ""
    assert body["reports"] == {"cio": None, "quant": None, "news": None, "social": None}


def test_get_report_detail_applies_same_normalization(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from app.api.main import app

    report_dir = tmp_path / "data" / "reports" / "20260403_120000_BTC"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text(
        json.dumps(
            {
                "symbol": "BTC",
                "timestamp": "2026-04-03T04:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.api.routes.reports.REPORTS_DIR", report_dir.parent)
    client = TestClient(app)
    response = client.get("/api/reports/20260403_120000_BTC")
    body = response.json()
    assert body["asset_type"] == "crypto"
    assert body["query"] == ""
    assert body["reports"] == {"cio": None, "quant": None, "news": None, "social": None}


def test_get_reports_normalizes_truthy_non_dict_reports(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from app.api.main import app

    report_dir = tmp_path / "data" / "reports" / "20260403_120000_BTC"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text(
        json.dumps(
            {
                "symbol": "BTC",
                "timestamp": "2026-04-03T04:00:00Z",
                "reports": "legacy-string",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.api.routes.reports.REPORTS_DIR", report_dir.parent)
    client = TestClient(app)

    response = client.get("/api/reports")
    body = response.json()[0]
    assert body["asset_type"] == "crypto"
    assert body["reports"] == {"cio": None, "quant": None, "news": None, "social": None}

    response = client.get("/api/reports/20260403_120000_BTC")
    body = response.json()
    assert body["asset_type"] == "crypto"
    assert body["reports"] == {"cio": None, "quant": None, "news": None, "social": None}


def test_get_reports_normalizes_list_reports_and_null_symbol(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from app.api.main import app

    report_dir = tmp_path / "data" / "reports" / "20260403_120000_X"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text(
        json.dumps(
            {
                "symbol": None,
                "asset_type": "crypto",
                "timestamp": "2026-04-03T04:00:00Z",
                "reports": ["legacy", "list"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.api.routes.reports.REPORTS_DIR", report_dir.parent)
    client = TestClient(app)

    response = client.get("/api/reports")
    body = response.json()[0]
    assert body["symbol"] == "UNKNOWN"
    assert body["asset_type"] == "crypto"
    assert body["reports"] == {"cio": None, "quant": None, "news": None, "social": None}

    response = client.get("/api/reports/20260403_120000_X")
    body = response.json()
    assert body["symbol"] == "UNKNOWN"
    assert body["asset_type"] == "crypto"
    assert body["reports"] == {"cio": None, "quant": None, "news": None, "social": None}
