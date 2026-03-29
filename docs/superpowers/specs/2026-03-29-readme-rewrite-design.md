# README Rewrite Design

**Date:** 2026-03-29
**Scope:** README.md and README.zh-CN.md

## Goal

Complete rewrite for clarity and conciseness. Fix stale script paths, remove non-existent script references, simplify structure, and limit Usage section to Web only.

## Structure

1. Title + one-line description
2. Features (6 core items)
3. Tech Stack
4. Quick Start (env setup + start all services)
5. Usage — Web only (frontend URL, API URL, API docs)
6. Scripts Reference (organized by subdirectory)
7. Project Layout
8. Architecture (diagram + inline data flow, no separate Data Flow section)
9. Code Quality
10. Contributing / License

## Key Changes

- Fix all script paths to new subdirectory structure (`scripts/startup/`, `scripts/utils/`, etc.)
- Remove non-existent script references: Polymarket, `inspect_event_memory.py`, `test_agent_history.py`
- Remove duplicate Frontend section in Project Layout
- Merge MCP server management (currently split across two sections)
- Remove hardcoded `PYTHONPATH=/home/wcqqq21/q-agents` from individual server commands
- Usage section: remove CLI interactive, Python one-shot, batch processing, daily harvester

## Decisions

- Usage = Web only (per user instruction)
- Scripts Reference section replaces scattered Advanced Features section
- Architecture diagram kept, Data Flow prose merged into Architecture description
