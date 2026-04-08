# Stock Switch K-Line Race Design

## Context

The stock chart already overlays the selected stock card quote onto the latest market-day candle, but the frontend still allows older OHLC responses to win after the user changes the selected stock. In practice this shows up as a brief correct chart flash that is later replaced by the previously selected stock's K-line. The lifted quote state also updates via an effect, so the chart can momentarily reuse the prior stock quote during a selection change.

## Goal

Keep the stock K-line tied to the currently selected card during rapid switching, without changing the backend API contract.

## Design

1. Add a small frontend-only "latest request wins" gate that can invalidate pending OHLC requests when the selected stock changes.
2. Use that gate inside `KLineChart` so only the newest request may update `ohlcData`, `loading`, and `error`.
3. Clear chart data immediately when the selected stock changes so the UI never keeps rendering the previous stock while the new request is loading.
4. Push the clicked stock quote upward immediately from `AssetSelector` so the chart's latest live-price overlay stays aligned with the card the user just selected.

## Non-Goals

- No backend changes.
- No new chart loading skeleton redesign.
- No refactor of general API fetching infrastructure outside the stock chart path.

## Validation

- Add a regression test for the latest-only request gate.
- Add source-level frontend regression coverage that `KLineChart` uses the request gate.
- Add source-level frontend regression coverage that `AssetSelector` immediately reports the clicked stock quote upward.
