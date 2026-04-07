# Daily Digest Email Content Refresh Design

## Goal

Refine the daily digest email so it is easier to scan and prioritizes macro context over technical prose.

The updated email must:

- compress the technical section into a lightweight ticker board
- expand macro news into the most important section of the email
- keep the CIO summary behavior unchanged

## User Decisions

- Keep the email in 3 sections only:
  1. technical overview
  2. macro news
  3. CIO summary
- Technical overview should show only:
  - ticker
  - current price
  - previous-session or trailing-24h percentage change
- Technical overview should not mention:
  - equity vs crypto labels
  - bullish/bearish/neutral labels
  - MACD, SMA, support, resistance, or longer narrative summaries
- Macro news should be the most detailed part of the email.
- Macro news should render exactly 3 items when available.
- Each macro news item should include:
  - title
  - 2-sentence summary
  - source
  - clickable link in HTML
  - plain URL in text
- CIO summary should remain unchanged.

## Scope

- Adjust the digest payload shape just enough to support a daily percentage change field for rendering.
- Update the email renderer for both plain text and HTML outputs.
- Reuse the existing macro-news source payload instead of redesigning the whole digest generator.
- Preserve existing scheduler, SMTP, and CIO behavior.

## Out Of Scope

- Rewriting the CIO prompt or CIO trimming logic
- Replacing the existing SMTP delivery path
- Changing digest scheduling or recipient configuration
- Building a richer article summarization pipeline with a second dedicated LLM pass
- Redesigning the persisted `digest.json` structure beyond the minimal field additions needed here

## Current Problem

The current digest email overweights technical commentary and underweights macro context:

- the technical section repeats asset-type and trend labels that the user can infer from the ticker list
- the technical section spends too many words on indicator commentary
- the macro section only renders short bullets without links or enough explanation

This makes the email feel inverted relative to the user goal of a daily macro-led briefing.

## Proposed Design

### 1. Technical Overview Rendering

Render one compact line per ticker in this shape:

```text
AAPL 254.48 (-1.23%)
BTC 68078.72 (+0.84%)
```

Rules:

- use `ticker` exactly as configured
- use `indicators.last_close` as the displayed current price
- use a new `daily_change_pct` field for the displayed change percentage
- format the displayed change percentage in the renderer, not the payload:
  - always show 2 decimal places
  - prepend `+` for positive values
  - prepend `-` for negative values
  - render `0.00%` for exact zero
- if the daily change is unavailable, render `--`
- do not show `asset_type`
- do not show `trend`
- do not show `summary`
- HTML output should color the percentage inline:
  - positive: green
  - negative: red
  - zero or unavailable: neutral gray

### 2. Daily Change Data Contract

Extend each `TechnicalSection` with:

```python
daily_change_pct: float | None
```

Generation rules:

- equities:
  - compute from the latest two valid closes in the same price source used by the digest technical adapter
- crypto:
  - compute from the latest two daily closes in the Yahoo-compatible path already used by the digest adapter
  - use the provider's daily candle boundary consistently, which in this implementation should be treated as UTC-based daily closes
- on unavailable data:
  - set `daily_change_pct` to `None`
  - do not fail the section solely because the field is missing

This field exists to support email rendering only. Existing richer technical fields remain available for JSON debugging and future use.

### 3. Macro News Rendering

Render macro news as the dominant section of the email.

For each of the top 3 news items, render:

- title
- 2 short explanatory sentences
- source label
- link

Rendering behavior:

- Prefer `snippet` content from `macro_news.sources[*]`
- Do not require an additional LLM summarization pass for these 2 sentences
- Build the 2-sentence block deterministically from existing source fields:
  - if `snippet` already contains 2 or more sentences, keep the first 2 sentences
  - if `snippet` contains exactly 1 sentence, use it as sentence 1 and append a deterministic sentence 2
  - if `snippet` is weak or missing, use deterministic fallback text for both sentences
- HTML output uses a clickable `<a>` tag
- text output shows the raw URL

Target structure:

```text
1. Hot jobs data pushes yields higher
Summary: Treasury yields moved up and stocks softened after stronger labor data reduced confidence in near-term rate cuts. This remains a macro watchpoint for today's cross-asset risk sentiment.
Source: MarketWatch
Link: https://...
```

The email should not promise explicit “what happened / why it matters” semantic extraction, because that would require a second article-level LLM summarization pass that is out of scope for this change.

### 4. CIO Summary

Keep the CIO section exactly as it is now:

- same generation path
- same placement at the end of the email
- same token and sentence controls

No prompt or contract changes are required for this revision.

## File Boundaries

- Modify: `app/digest/models.py`
  - add `daily_change_pct` to `TechnicalSection`
- Modify: `app/digest/technical.py`
  - compute and populate `daily_change_pct`
- Modify: `app/digest/render.py`
  - redesign both text and HTML rendering
- Modify: `tests/digest/test_render.py`
  - lock the new section shapes
- Modify: `tests/digest/test_generator.py`
  - lock `daily_change_pct` generation and rendering fallbacks

No changes are expected in:

- `app/digest/cio.py`
- `app/digest/generator.py`
- `app/services/email_service.py`

## Error Handling

- if `daily_change_pct` is unavailable:
  - render `--`
  - do not fail email generation
- if a macro news article is missing `url`:
  - render the exact string `Link unavailable` in both text and HTML
- if a macro news article is missing `snippet`:
  - render the exact 2-sentence fallback:
    - `Summary unavailable from the upstream news feed. This remains a macro watchpoint worth checking in the original article.`
- if a macro news article has exactly 1 snippet sentence:
  - append the exact second sentence:
    - `This remains a macro watchpoint for today's cross-asset risk sentiment.`
- if the macro news section itself is already in error:
  - keep the current “unavailable” behavior

## Testing Strategy

Use TDD for the behavior change:

1. update render tests first
2. verify old rendering fails the new assertions
3. update technical-section tests or generator tests for `daily_change_pct`
4. implement minimal code
5. rerun digest-focused tests
6. run one real send for manual inspection after automated verification passes

Required automated verification:

- `uv run python -m pytest tests/digest/test_render.py tests/digest/test_generator.py -q`
- `uv run ruff check app/digest/render.py app/digest/technical.py app/digest/models.py tests/digest/test_render.py tests/digest/test_generator.py`
- `uv run ruff format --check app/digest/render.py app/digest/technical.py app/digest/models.py tests/digest/test_render.py tests/digest/test_generator.py`
