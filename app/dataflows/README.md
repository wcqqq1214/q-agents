# Data Provider Abstraction Layer

## Overview

Provider-agnostic data interface that allows switching between MCP, yfinance, Polygon, and Alpha Vantage without changing agent code.

## Architecture

```
Agent → DataFlowRouter → [Cache?] → Provider → External API
                    ↓ (on error)
                    Fallback Provider
```

## Quick Start

```python
from app.dataflows.interface import DataFlowRouter

router = DataFlowRouter()
data = await router.get_stock_data("AAPL", start, end)
```

## Configuration

See `config.py` for:
- Data vendor selection (MCP/yfinance/polygon)
- Cache TTL settings
- MCP server URLs
- API keys

## Adding New Providers

1. Create `providers/new_provider.py`
2. Inherit from `BaseDataProvider`
3. Implement all abstract methods
4. Return standardized Pydantic models
5. Add to `_PROVIDER_REGISTRY` in `interface.py`

## Testing

```bash
# Unit tests
uv run pytest tests/test_dataflows_*.py

# Integration tests (requires Redis + MCP servers)
uv run pytest tests/integration/ -m integration
```
