# Stock K-Line Quote Fallback Design

## Problem

The previous MCP-history fallback is not sufficient in the live environment. The current runtime now shows:

- persisted stock daily rows stop at `2026-04-07`
- `call_get_stock_history("AAPL", ..., "2026-04-08")` still returns only up to `2026-04-07`
- `call_get_us_stock_quote("AAPL")` already exposes the `2026-04-08` intraday fields needed to construct a same-day daily candle

As a result, the chart still misses the current America/New_York market-date candle even though quote data is available.

## Goal

When the current US market day is ahead of both the database and the MCP history endpoint, synthesize a temporary daily OHLC row from the live quote payload and use it for both scheduled stock refreshes and `/api/stocks/{symbol}/ohlc`.

## Approach

- Keep the existing MCP-history refresh path.
- Add a quote-to-daily-candle helper that converts the live quote into a same-day daily OHLC row for the current America/New_York market date.
- Use the synthetic candle only when:
  - the symbol is a stock,
  - today is an NYSE trading day,
  - the latest known daily row is still older than the current market date,
  - the quote has enough fields to build a candle.

## Fields

The synthetic daily candle will use:

- `date`: current market date in `America/New_York`
- `open`: quote `open` when present, otherwise `previous_close`/`price`
- `high`: quote `day_high` when present, otherwise `max(open, close)`
- `low`: quote `day_low` when present, otherwise `min(open, close)`
- `close`: quote `price`
- `volume`: quote `volume` or `0`

## Scope

- `app/services/stock_updater.py`
- `app/api/routes/ohlc.py`
- regression tests for both paths
