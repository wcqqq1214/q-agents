from mcp_servers.common.tool_errors import build_tool_error_payload
from mcp_servers.news_search.main import search_news_with_duckduckgo


def test_build_tool_error_payload_marks_rate_limit_retryable():
    payload = build_tool_error_payload(
        provider_name="Yahoo Finance",
        tool_name="get_stock_history",
        exc=RuntimeError("429 rate limit exceeded"),
        base_payload={"ticker": "AAPL", "data": []},
    )

    assert payload["retryable"] is True
    assert payload["retry_after_seconds"] == 10
    assert "Wait about 10 seconds" in payload["error"]


def test_news_search_tool_returns_friendly_error(monkeypatch):
    def boom(query: str, limit: int):
        raise RuntimeError("upstream service unavailable")

    monkeypatch.setattr("mcp_servers.news_search.main.ddg_search", boom)

    payload = search_news_with_duckduckgo("AAPL", 3)

    assert payload["articles"] == []
    assert payload["retryable"] is True
    assert payload["source"] == "duckduckgo"
