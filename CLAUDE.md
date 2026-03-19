# Finance Agent Project

## Python Environment

This project uses **uv** for Python environment management.

**IMPORTANT:** Always use `uv run python` instead of `python` or `python3` when running Python commands.

Examples:
```bash
# Run Python scripts
uv run python script.py

# Run Python commands
uv run python -c "import module; print('test')"

# Run pytest
uv run pytest tests/

# Run uvicorn
uv run uvicorn app.api.main:app --port 8080
```

## Project Structure

- `app/` - Backend FastAPI application
- `frontend/` - Next.js frontend application
- `docs/` - Documentation and specifications
