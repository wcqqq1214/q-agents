# Scripts Reorganization Design

**Date:** 2026-03-29
**Status:** Approved

## Goal

Reorganize `scripts/` from a flat directory of 21 files into 5 subdirectories aligned with the existing `app/` module structure.

## Directory Mapping

### `scripts/startup/` — Service lifecycle
- `start_all.sh`
- `stop_all.sh`
- `start_api.sh`
- `start_mcp_servers.sh`
- `stop_mcp_servers.sh`
- `start_frontend.sh`

### `scripts/data/` — Data acquisition and maintenance
- `download_stock_data.py`
- `download_crypto_data.py`
- `daily_harvester.py`
- `merge_duplicate_symbols.py`
- `clean_crypto_data.py`
- `optimize_crypto_indexes.py`

### `scripts/ml/` — ML pipeline
- `run_ml_quant_metrics.py`
- `batch_process.py`
- `process_layer1.py`

### `scripts/rag/` — Event memory / RAG
- `build_event_memory_batch.py`
- `export_events.py`
- `query_event_memory.py`
- `list_tickers.py`

### `scripts/utils/` — Tools and testing
- `test_dataflows.py`
- `manual_run.py`

## Files That Need Path Updates

1. `CLAUDE.md` — all `bash scripts/*.sh` and `uv run python scripts/*.py` references
2. `scripts/startup/start_all.sh` — internal calls to other shell scripts
3. `scripts/startup/stop_all.sh` — if it calls other scripts internally

## Out of Scope

- No scripts are deleted (all 21 are retained)
- No script content is modified beyond internal path references
