# Crypto Historical Data Download

## Overview

This project uses **Binance Vision** public data archive to download historical cryptocurrency K-line (OHLC) data instead of API calls.

## Data Source

- **Source**: [data.binance.vision](https://data.binance.vision)
- **Type**: Monthly archived K-line data (ZIP files containing CSV)
- **Advantages**:
  - Free and public (no API key required)
  - Complete historical data from 2020 onwards
  - No rate limits
  - Official Binance data archive

## Download Script

### Quick Start

```bash
# 1. Clean old data (optional, if you have old OKX data)
uv run python scripts/clean_crypto_data.py

# 2. Download historical data
uv run python scripts/download_binance_vision.py
```

### Usage

```bash
# Download all historical data (2020-2025)
uv run python scripts/download_binance_vision.py
```

### Configuration

Edit `scripts/download_binance_vision.py` to customize:

```python
SYMBOLS = ["BTCUSDT", "ETHUSDT"]  # Add more symbols
INTERVALS = {
    "15m": "15m",  # 15-minute candles
    "1h": "1H",    # 1-hour candles
    "4h": "4H",    # 4-hour candles
    "1d": "1D",    # Daily candles
    "1w": "1W",    # Weekly candles
    "1M": "1M"     # Monthly candles
}
START_YEAR = 2020
END_YEAR = 2025
```

**Note**: Binance doesn't provide 1-year interval. Use 1M (monthly) for long-term analysis.

### Data Volume

Optimized configuration (15m, 1h, 4h, 1d, 1w, 1M):
- **Per symbol**: ~232,000 records (5 years)
- **2 symbols**: ~464,000 records
- **Database size**: ~44 MB
- **Download time**: ~5-10 minutes

If you need higher frequency data (1m, 5m), add them to `INTERVALS`, but note:
- 1m data: +2.6M records per symbol (+250 MB)
- 5m data: +525K records per symbol (+50 MB)

### What It Does

1. Downloads monthly K-line ZIP files from Binance Vision
2. Extracts and parses CSV data (handles missing headers)
3. Converts timestamps from milliseconds to ISO format
4. Stores data in SQLite database (`data/finance_data.db`)
5. Updates metadata table with date ranges and record counts

### Data Format

**Binance CSV columns** (no header):
- open_time (ms timestamp)
- open, high, low, close, volume
- close_time, quote_asset_volume, number_of_trades
- taker_buy_base_asset_volume, taker_buy_quote_asset_volume, ignore

**Database storage** (`crypto_ohlc` table):
- symbol: e.g., 'BTC-USDT'
- timestamp: milliseconds since epoch
- date: ISO format datetime string
- open, high, low, close, volume
- bar: interval code (e.g., '1m', '1H', '1D')

## Database Schema

```sql
CREATE TABLE crypto_ohlc (
    symbol        TEXT NOT NULL,
    timestamp     INTEGER NOT NULL,
    date          TEXT NOT NULL,
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    volume        REAL,
    bar           TEXT NOT NULL,
    PRIMARY KEY (symbol, timestamp, bar)
);

CREATE TABLE crypto_metadata (
    symbol        TEXT NOT NULL,
    bar           TEXT NOT NULL,
    last_update   TEXT,
    data_start    TEXT,
    data_end      TEXT,
    total_records INTEGER,
    PRIMARY KEY (symbol, bar)
);
```

## Migration Notes

### Replaced Scripts

- ❌ `scripts/fetch_crypto_ohlc.py` (deleted - used OKX API)
- ✅ `scripts/download_binance_vision.py` (new - uses Binance Vision)

### OKX API Still Used For

The OKX API integration (`app/api/routes/okx.py`) is **still active** for:
- Real-time trading operations
- Account balance queries
- Order placement and management
- Live market data

Only the **historical data download** has been migrated to Binance Vision.

## Expected Download Time

- **Per symbol/interval**: ~30-60 seconds (depends on network speed)
- **Full download** (2 symbols × 6 intervals): ~5-10 minutes
- **Data size**: ~44 MB total (optimized intervals)

## Troubleshooting

### 404 Errors

Some months may not have data (especially early 2020 or future months). This is normal and logged as debug messages.

### Timeout Errors

If downloads timeout, the script will log errors and continue. You can re-run the script - it uses `ON CONFLICT` to avoid duplicates.

### Verify Data

```bash
# Check database
sqlite3 data/finance_data.db "SELECT symbol, bar, total_records, data_start, data_end FROM crypto_metadata;"

# Query sample data
sqlite3 data/finance_data.db "SELECT * FROM crypto_ohlc WHERE symbol='BTC-USDT' AND bar='1d' LIMIT 10;"
```

## Future Enhancements

- [ ] Add incremental update mode (only download latest month)
- [ ] Support for futures/perpetual contracts
- [ ] Data validation and cleaning pipeline
- [ ] Automated daily/weekly updates via cron
