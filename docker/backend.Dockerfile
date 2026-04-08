# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY . .
RUN uv sync --frozen --no-dev

FROM base AS api
EXPOSE 8080
CMD ["uv", "run", "python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM base AS market-data-mcp
EXPOSE 8000
CMD ["uv", "run", "python", "-m", "mcp_servers.market_data.main"]

FROM base AS news-search-mcp
EXPOSE 8001
CMD ["uv", "run", "python", "-m", "mcp_servers.news_search.main"]
