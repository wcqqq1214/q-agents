from __future__ import annotations

from typing import Sequence, TypedDict

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from app.database.schema import DEFAULT_TICKER_CATALOG, get_ticker_peer_groups

DEFAULT_SIMILARITY_WINDOW = 7
DEFAULT_SIMILARITY_TOP_K = 8
DEFAULT_SIMILARITY_HORIZON_DAYS = 3

SIMILARITY_EXCLUDE_COLS = {
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "news_text_blob",
}

DEFAULT_PEER_GROUP_BY_SYMBOL = {
    symbol: peer_group for symbol, _, peer_group in DEFAULT_TICKER_CATALOG
}


class SimilarPeriod(TypedDict, total=False):
    """Single matched historical period."""

    symbol: str
    start_date: str
    end_date: str
    similarity: float
    future_return_3d: float
    positive_outcome: bool
    target_hit: bool
    scope: str
    peer_group: str


class HistoricalSimilaritySummary(TypedDict, total=False):
    """Summary of historical periods most similar to the latest market state."""

    window_size: int
    horizon_days: int
    query_symbol: str
    query_start_date: str
    query_end_date: str
    n_matches: int
    avg_similarity: float
    avg_future_return_3d: float
    positive_rate: float
    target_hit_rate: float
    query_peer_group: str
    same_symbol_matches: int
    peer_group_matches: int
    market_matches: int
    cross_symbol_matches: int
    strategy: str
    matches: list[SimilarPeriod]


def load_ticker_peer_groups() -> dict[str, str]:
    """Load peer-group metadata from the database with static fallback defaults."""

    peer_group_map = dict(DEFAULT_PEER_GROUP_BY_SYMBOL)
    try:
        peer_group_map.update(get_ticker_peer_groups())
    except Exception:
        pass
    return peer_group_map


def infer_peer_group(symbol: str, peer_group_map: dict[str, str] | None = None) -> str:
    """Return a curated peer-group label for the symbol."""

    normalized = str(symbol or "").strip().upper()
    mapping = peer_group_map if peer_group_map is not None else load_ticker_peer_groups()
    return mapping.get(normalized, "unknown")


def _infer_similarity_feature_columns(frame: pd.DataFrame) -> list[str]:
    """Select numeric feature columns suitable for similarity matching."""

    cols: list[str] = []
    for col in frame.columns:
        if col in SIMILARITY_EXCLUDE_COLS or col.startswith("target_"):
            continue
        if pd.api.types.is_numeric_dtype(frame[col]):
            cols.append(col)
    return cols


def _build_window_endpoints(
    history: pd.DataFrame,
    feature_columns: Sequence[str],
    *,
    window_size: int,
    future_horizon_days: int,
    target_col: str | None = None,
) -> pd.DataFrame:
    """Convert row-wise panel features into window endpoints with rolling means."""

    frames: list[pd.DataFrame] = []
    required_cols = ["symbol", "trade_date", "close", *feature_columns]
    if target_col:
        required_cols.append(target_col)

    for symbol, group in history[required_cols].groupby("symbol", sort=False):
        ordered = group.sort_values("trade_date").reset_index(drop=True).copy()
        rolling = (
            ordered[list(feature_columns)]
            .rolling(window=window_size, min_periods=window_size)
            .mean()
        )
        rolling.columns = [str(col) for col in feature_columns]

        frame = ordered[["symbol", "trade_date"]].copy()
        frame["window_start_date"] = ordered["trade_date"].shift(window_size - 1)
        frame["future_return_3d"] = (
            ordered["close"].shift(-future_horizon_days) / ordered["close"] - 1.0
        )
        if target_col and target_col in ordered.columns:
            frame["target_hit"] = ordered[target_col]

        frame = pd.concat([frame, rolling], axis=1)
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def find_similar_historical_periods(
    history: pd.DataFrame,
    query: pd.DataFrame,
    *,
    feature_columns: Sequence[str] | None = None,
    window_size: int = DEFAULT_SIMILARITY_WINDOW,
    top_k: int = DEFAULT_SIMILARITY_TOP_K,
    future_horizon_days: int = DEFAULT_SIMILARITY_HORIZON_DAYS,
    target_col: str = "target_up_big_move_t3",
) -> HistoricalSimilaritySummary:
    """Find the most similar historical panel windows to the latest query window."""

    if history.empty or query.empty:
        return HistoricalSimilaritySummary(matches=[], n_matches=0, strategy="none")

    history_frame = history.copy()
    query_frame = query.copy()
    history_frame["trade_date"] = pd.to_datetime(history_frame["trade_date"])
    query_frame["trade_date"] = pd.to_datetime(query_frame["trade_date"])
    history_frame = history_frame.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    query_frame = query_frame.sort_values("trade_date").reset_index(drop=True)

    query_window = query_frame.tail(min(window_size, len(query_frame))).copy()
    effective_window_size = len(query_window)
    if effective_window_size < 2:
        return HistoricalSimilaritySummary(matches=[], n_matches=0, strategy="none")

    if feature_columns is None:
        history_cols = set(_infer_similarity_feature_columns(history_frame))
        query_cols = set(_infer_similarity_feature_columns(query_window))
        feature_columns = sorted(history_cols & query_cols)

    feature_columns = [str(col) for col in feature_columns]
    if not feature_columns:
        return HistoricalSimilaritySummary(matches=[], n_matches=0, strategy="none")

    endpoints = _build_window_endpoints(
        history_frame,
        feature_columns,
        window_size=effective_window_size,
        future_horizon_days=future_horizon_days,
        target_col=target_col,
    )
    if endpoints.empty:
        return HistoricalSimilaritySummary(matches=[], n_matches=0, strategy="none")

    peer_group_map = load_ticker_peer_groups()
    query_symbol = ""
    if "symbol" in query_window.columns and query_window["symbol"].nunique() == 1:
        query_symbol = str(query_window["symbol"].iloc[-1])
    query_peer_group = infer_peer_group(query_symbol, peer_group_map) if query_symbol else "unknown"
    query_start_date = pd.Timestamp(query_window["trade_date"].min())
    query_end_date = pd.Timestamp(query_window["trade_date"].max())

    candidate_mask = endpoints["trade_date"] < query_end_date
    if query_symbol:
        candidate_mask &= ~(
            (endpoints["symbol"].astype(str) == query_symbol)
            & (pd.to_datetime(endpoints["trade_date"]) >= query_start_date)
        )

    candidates = endpoints.loc[candidate_mask].copy()
    candidates = candidates.dropna(
        subset=["window_start_date", "future_return_3d", *feature_columns]
    )
    if candidates.empty:
        return HistoricalSimilaritySummary(
            window_size=effective_window_size,
            horizon_days=future_horizon_days,
            query_symbol=query_symbol,
            query_peer_group=query_peer_group,
            query_start_date=query_start_date.strftime("%Y-%m-%d"),
            query_end_date=query_end_date.strftime("%Y-%m-%d"),
            matches=[],
            n_matches=0,
            same_symbol_matches=0,
            peer_group_matches=0,
            market_matches=0,
            cross_symbol_matches=0,
            strategy="none",
        )

    candidate_matrix = candidates[feature_columns].to_numpy(dtype=float)
    query_vector = query_window[feature_columns].mean().to_numpy(dtype=float).reshape(1, -1)

    mean = np.nanmean(candidate_matrix, axis=0)
    std = np.nanstd(candidate_matrix, axis=0)
    std[std == 0] = 1.0

    candidate_matrix = np.nan_to_num(
        (candidate_matrix - mean) / std, nan=0.0, posinf=0.0, neginf=0.0
    )
    query_vector = np.nan_to_num((query_vector - mean) / std, nan=0.0, posinf=0.0, neginf=0.0)
    scores = cosine_similarity(candidate_matrix, query_vector).ravel()

    scored = candidates.assign(
        similarity=scores,
        peer_group=candidates["symbol"]
        .astype(str)
        .str.upper()
        .map(peer_group_map)
        .fillna("unknown"),
    ).sort_values("similarity", ascending=False)
    same_symbol_scored = pd.DataFrame(columns=scored.columns)
    peer_group_scored = pd.DataFrame(columns=scored.columns)
    market_scored = scored
    if query_symbol:
        same_symbol_scored = scored.loc[scored["symbol"].astype(str) == query_symbol]
        non_same_symbol = scored.loc[scored["symbol"].astype(str) != query_symbol]
        if query_peer_group != "unknown":
            peer_group_scored = non_same_symbol.loc[
                non_same_symbol["peer_group"] == query_peer_group
            ]
            market_scored = non_same_symbol.loc[non_same_symbol["peer_group"] != query_peer_group]
        else:
            market_scored = non_same_symbol

    same_symbol_top = same_symbol_scored.head(top_k)
    remaining_after_same = max(top_k - len(same_symbol_top), 0)
    peer_group_top = peer_group_scored.head(remaining_after_same)
    remaining_after_peer = max(remaining_after_same - len(peer_group_top), 0)
    market_top = market_scored.head(remaining_after_peer)
    top = pd.concat([same_symbol_top, peer_group_top, market_top], ignore_index=True)

    matches: list[SimilarPeriod] = []
    for row in top.itertuples(index=False):
        target_hit = getattr(row, "target_hit", np.nan)
        future_return = float(row.future_return_3d)
        symbol = str(row.symbol)
        if query_symbol and symbol == query_symbol:
            scope = "same_symbol"
        elif (
            query_peer_group != "unknown"
            and getattr(row, "peer_group", "unknown") == query_peer_group
        ):
            scope = "peer_group"
        else:
            scope = "market"
        matches.append(
            SimilarPeriod(
                symbol=symbol,
                start_date=pd.Timestamp(row.window_start_date).strftime("%Y-%m-%d"),
                end_date=pd.Timestamp(row.trade_date).strftime("%Y-%m-%d"),
                similarity=float(row.similarity),
                future_return_3d=future_return,
                positive_outcome=bool(future_return > 0),
                target_hit=bool(target_hit) if pd.notna(target_hit) else False,
                scope=scope,
                peer_group=str(getattr(row, "peer_group", "unknown")),
            )
        )

    similarity_values = [match["similarity"] for match in matches]
    future_returns = [match["future_return_3d"] for match in matches]
    positive_rate = (
        float(np.mean([match["positive_outcome"] for match in matches])) if matches else 0.0
    )
    target_hit_rate = float(np.mean([match["target_hit"] for match in matches])) if matches else 0.0
    same_symbol_matches = sum(1 for match in matches if match.get("scope") == "same_symbol")
    peer_group_matches = sum(1 for match in matches if match.get("scope") == "peer_group")
    market_matches = sum(1 for match in matches if match.get("scope") == "market")
    cross_symbol_matches = peer_group_matches + market_matches
    if same_symbol_matches and peer_group_matches and market_matches:
        strategy = "same_symbol_then_peer_group_then_market"
    elif same_symbol_matches and peer_group_matches:
        strategy = "same_symbol_then_peer_group"
    elif same_symbol_matches and market_matches:
        strategy = "same_symbol_then_market"
    elif peer_group_matches and market_matches:
        strategy = "peer_group_then_market"
    elif same_symbol_matches:
        strategy = "same_symbol_only"
    elif peer_group_matches:
        strategy = "peer_group_only"
    elif market_matches:
        strategy = "market_only"
    else:
        strategy = "none"

    return HistoricalSimilaritySummary(
        window_size=effective_window_size,
        horizon_days=future_horizon_days,
        query_symbol=query_symbol,
        query_peer_group=query_peer_group,
        query_start_date=query_start_date.strftime("%Y-%m-%d"),
        query_end_date=query_end_date.strftime("%Y-%m-%d"),
        n_matches=len(matches),
        avg_similarity=float(np.mean(similarity_values)) if similarity_values else 0.0,
        avg_future_return_3d=float(np.mean(future_returns)) if future_returns else 0.0,
        positive_rate=positive_rate,
        target_hit_rate=target_hit_rate,
        same_symbol_matches=same_symbol_matches,
        peer_group_matches=peer_group_matches,
        market_matches=market_matches,
        cross_symbol_matches=cross_symbol_matches,
        strategy=strategy,
        matches=matches,
    )
