"""Contract tests for the repository's container deployment surface."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docker_compose_defines_full_container_stack() -> None:
    """Compose file should define the full five-service deployment topology."""
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    for service in (
        "redis:",
        "market-data-mcp:",
        "news-search-mcp:",
        "api:",
        "frontend:",
    ):
        assert service in compose

    assert "redis_data:" in compose
    assert "redis://redis:6379/0" in compose
    assert "http://market-data-mcp:8000/mcp" in compose
    assert "http://news-search-mcp:8001/mcp" in compose
    assert "NEXT_PUBLIC_API_URL" in compose
    assert "http://localhost:8080" in compose


def test_backend_dockerfile_exposes_named_python_service_targets() -> None:
    """Backend Dockerfile should expose dedicated targets for each Python service."""
    backend_dockerfile = REPO_ROOT / "docker" / "backend.Dockerfile"
    assert backend_dockerfile.exists()

    dockerfile = backend_dockerfile.read_text(encoding="utf-8")
    assert "ghcr.io/astral-sh/uv" in dockerfile
    assert "FROM base AS api" in dockerfile
    assert "FROM base AS market-data-mcp" in dockerfile
    assert "FROM base AS news-search-mcp" in dockerfile


def test_frontend_dockerfile_builds_and_runs_production_app() -> None:
    """Frontend Dockerfile should install with pnpm and start the production server."""
    frontend_dockerfile = REPO_ROOT / "docker" / "frontend.Dockerfile"
    assert frontend_dockerfile.exists()

    dockerfile = frontend_dockerfile.read_text(encoding="utf-8")
    assert "corepack" in dockerfile
    assert "pnpm install" in dockerfile
    assert "pnpm build" in dockerfile
    assert "pnpm" in dockerfile
    assert "start" in dockerfile
    assert "--hostname" in dockerfile
    assert "0.0.0.0" in dockerfile
    assert "--port" in dockerfile
    assert "3000" in dockerfile
