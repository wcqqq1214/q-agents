# Scripts Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `scripts/` from a flat directory of 21 files into 5 subdirectories (`startup/`, `data/`, `ml/`, `rag/`, `utils/`) aligned with the `app/` module structure.

**Architecture:** Move files with `git mv` to preserve history, then update internal cross-script references in `start_all.sh` / `stop_all.sh` (both already use `$SCRIPT_DIR` so they only need to call sibling scripts in the same `startup/` directory — no path changes needed there). Update `CLAUDE.md` to reflect new paths.

**Tech Stack:** bash, git

---

## File Map

| Action | Path |
|--------|------|
| Create dir | `scripts/startup/` |
| Create dir | `scripts/data/` |
| Create dir | `scripts/ml/` |
| Create dir | `scripts/rag/` |
| Create dir | `scripts/utils/` |
| Move | `scripts/*.sh` → `scripts/startup/` |
| Move | `scripts/download_*.py`, `scripts/daily_harvester.py`, `scripts/merge_duplicate_symbols.py`, `scripts/clean_crypto_data.py`, `scripts/optimize_crypto_indexes.py` → `scripts/data/` |
| Move | `scripts/run_ml_quant_metrics.py`, `scripts/batch_process.py`, `scripts/process_layer1.py` → `scripts/ml/` |
| Move | `scripts/build_event_memory_batch.py`, `scripts/export_events.py`, `scripts/query_event_memory.py`, `scripts/list_tickers.py` → `scripts/rag/` |
| Move | `scripts/test_dataflows.py`, `scripts/manual_run.py` → `scripts/utils/` |
| Modify | `CLAUDE.md` — update all script path references |

---

## Task 1: Move startup scripts

**Files:**
- Move: `scripts/*.sh` → `scripts/startup/`

- [ ] **Step 1: Move all shell scripts**

```bash
cd /home/wcqqq21/q-agents
git mv scripts/start_all.sh scripts/startup/start_all.sh
git mv scripts/stop_all.sh scripts/startup/stop_all.sh
git mv scripts/start_api.sh scripts/startup/start_api.sh
git mv scripts/start_mcp_servers.sh scripts/startup/start_mcp_servers.sh
git mv scripts/stop_mcp_servers.sh scripts/startup/stop_mcp_servers.sh
git mv scripts/start_frontend.sh scripts/startup/start_frontend.sh
```

- [ ] **Step 2: Verify files are in place**

```bash
ls scripts/startup/
```

Expected output:
```
start_all.sh  start_api.sh  start_frontend.sh  start_mcp_servers.sh  stop_all.sh  stop_mcp_servers.sh
```

- [ ] **Step 3: Verify start_all.sh still works (dry run)**

`start_all.sh` calls sibling scripts via `$SCRIPT_DIR/start_mcp_servers.sh` etc. Since all `.sh` files are now in the same `startup/` directory, `$SCRIPT_DIR` resolves correctly — no content changes needed.

```bash
bash -n scripts/startup/start_all.sh && echo "syntax OK"
bash -n scripts/startup/stop_all.sh && echo "syntax OK"
```

Expected: `syntax OK` for both.

- [ ] **Step 4: Commit**

```bash
git add -A scripts/startup/
git commit -m "refactor(scripts): move shell scripts to startup/"
```

---

## Task 2: Move data scripts

**Files:**
- Move: 6 data-related Python scripts → `scripts/data/`

- [ ] **Step 1: Move data scripts**

```bash
cd /home/wcqqq21/q-agents
git mv scripts/download_stock_data.py scripts/data/download_stock_data.py
git mv scripts/download_crypto_data.py scripts/data/download_crypto_data.py
git mv scripts/daily_harvester.py scripts/data/daily_harvester.py
git mv scripts/merge_duplicate_symbols.py scripts/data/merge_duplicate_symbols.py
git mv scripts/clean_crypto_data.py scripts/data/clean_crypto_data.py
git mv scripts/optimize_crypto_indexes.py scripts/data/optimize_crypto_indexes.py
```

- [ ] **Step 2: Verify**

```bash
ls scripts/data/
```

Expected:
```
clean_crypto_data.py  daily_harvester.py  download_crypto_data.py  download_stock_data.py  merge_duplicate_symbols.py  optimize_crypto_indexes.py
```

- [ ] **Step 3: Commit**

```bash
git add -A scripts/data/
git commit -m "refactor(scripts): move data scripts to data/"
```

---

## Task 3: Move ML scripts

**Files:**
- Move: 3 ML scripts → `scripts/ml/`

- [ ] **Step 1: Move ML scripts**

```bash
cd /home/wcqqq21/q-agents
git mv scripts/run_ml_quant_metrics.py scripts/ml/run_ml_quant_metrics.py
git mv scripts/batch_process.py scripts/ml/batch_process.py
git mv scripts/process_layer1.py scripts/ml/process_layer1.py
```

- [ ] **Step 2: Verify**

```bash
ls scripts/ml/
```

Expected:
```
batch_process.py  process_layer1.py  run_ml_quant_metrics.py
```

- [ ] **Step 3: Commit**

```bash
git add -A scripts/ml/
git commit -m "refactor(scripts): move ML scripts to ml/"
```

---

## Task 4: Move RAG scripts

**Files:**
- Move: 4 RAG scripts → `scripts/rag/`

- [ ] **Step 1: Move RAG scripts**

```bash
cd /home/wcqqq21/q-agents
git mv scripts/build_event_memory_batch.py scripts/rag/build_event_memory_batch.py
git mv scripts/export_events.py scripts/rag/export_events.py
git mv scripts/query_event_memory.py scripts/rag/query_event_memory.py
git mv scripts/list_tickers.py scripts/rag/list_tickers.py
```

- [ ] **Step 2: Verify**

```bash
ls scripts/rag/
```

Expected:
```
build_event_memory_batch.py  export_events.py  list_tickers.py  query_event_memory.py
```

- [ ] **Step 3: Commit**

```bash
git add -A scripts/rag/
git commit -m "refactor(scripts): move RAG scripts to rag/"
```

---

## Task 5: Move utility scripts

**Files:**
- Move: 2 utility scripts → `scripts/utils/`

- [ ] **Step 1: Move utility scripts**

```bash
cd /home/wcqqq21/q-agents
git mv scripts/test_dataflows.py scripts/utils/test_dataflows.py
git mv scripts/manual_run.py scripts/utils/manual_run.py
```

- [ ] **Step 2: Verify scripts/ root is now empty (except __pycache__)**

```bash
ls scripts/
```

Expected:
```
data/  ml/  rag/  startup/  utils/
```

(A `__pycache__/` may also appear — that's fine.)

- [ ] **Step 3: Commit**

```bash
git add -A scripts/utils/
git commit -m "refactor(scripts): move utility scripts to utils/"
```

---

## Task 6: Update CLAUDE.md path references

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Find all script references in CLAUDE.md**

```bash
grep -n "scripts/" CLAUDE.md
```

Note every line number that references a script path.

- [ ] **Step 2: Update startup script paths**

In `CLAUDE.md`, replace:
```
bash scripts/start_all.sh
bash scripts/stop_all.sh
bash scripts/start_api.sh
bash scripts/start_mcp_servers.sh
bash scripts/stop_mcp_servers.sh
bash scripts/start_frontend.sh
```
with:
```
bash scripts/startup/start_all.sh
bash scripts/startup/stop_all.sh
bash scripts/startup/start_api.sh
bash scripts/startup/start_mcp_servers.sh
bash scripts/startup/stop_mcp_servers.sh
bash scripts/startup/start_frontend.sh
```

- [ ] **Step 3: Update Python script paths**

Replace every `uv run python scripts/<name>.py` reference with its new subdirectory path. Based on the spec:

| Old | New |
|-----|-----|
| `uv run python scripts/build_event_memory_batch.py` | `uv run python scripts/rag/build_event_memory_batch.py` |
| `uv run python scripts/run_ml_quant_metrics.py` | `uv run python scripts/ml/run_ml_quant_metrics.py` |
| `uv run python scripts/download_crypto_data.py` | `uv run python scripts/data/download_crypto_data.py` |
| `uv run python -m scripts.manual_run` | `uv run python -m scripts.utils.manual_run` |

- [ ] **Step 4: Verify no stale references remain**

```bash
grep -n "scripts/[a-z]" CLAUDE.md | grep -v "scripts/startup\|scripts/data\|scripts/ml\|scripts/rag\|scripts/utils"
```

Expected: no output (all references updated).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md script paths after reorganization"
```

---

## Task 7: Final verification

- [ ] **Step 1: Confirm directory structure**

```bash
find scripts/ -type f | sort
```

Expected — all 21 files under their new subdirectories, nothing in `scripts/` root except subdirs.

- [ ] **Step 2: Spot-check a startup script still resolves siblings correctly**

```bash
bash -n scripts/startup/start_all.sh && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Confirm git history preserved for a sample file**

```bash
git log --oneline --follow scripts/startup/start_all.sh | head -5
```

Expected: shows commits predating this reorganization (history preserved via `git mv`).
