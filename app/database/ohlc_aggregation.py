"""OHLC data aggregation utilities."""

from typing import List, Dict, Any
from datetime import datetime, timedelta
import pandas as pd


def aggregate_ohlc(
    data: List[Dict[str, Any]],
    target_interval: str
) -> List[Dict[str, Any]]:
    """
    Aggregate OHLC data to a larger time interval.

    Args:
        data: List of OHLC records with 1-minute granularity
        target_interval: Target interval (5m, 15m, 30m, 1h, 4h, 1d, 1w)

    Returns:
        Aggregated OHLC data
    """
    if not data:
        return []

    # Convert to DataFrame
    df = pd.DataFrame(data)

    # Convert timestamp to datetime
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df = df.set_index('datetime')

    # Map interval to pandas frequency
    interval_to_freq = {
        '5m': '5T',    # 5 minutes
        '15m': '15T',  # 15 minutes
        '30m': '30T',  # 30 minutes
        '1h': '1H',    # 1 hour
        '4h': '4H',    # 4 hours
        '1d': '1D',    # 1 day
        '1w': '1W',    # 1 week
    }

    freq = interval_to_freq.get(target_interval)
    if not freq:
        # If interval not supported, return original data
        return data

    # Resample and aggregate
    # - open: first value in period
    # - high: max value in period
    # - low: min value in period
    # - close: last value in period
    # - volume: sum of volumes in period
    aggregated = df.resample(freq).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'symbol': 'first',
        'bar': 'first'
    }).dropna()

    # Convert back to list of dicts
    result = []
    for idx, row in aggregated.iterrows():
        result.append({
            'symbol': row['symbol'],
            'timestamp': int(idx.timestamp() * 1000),
            'date': idx.isoformat(),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': float(row['volume']),
            'bar': target_interval
        })

    return result
