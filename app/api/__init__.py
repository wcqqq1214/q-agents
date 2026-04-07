"""FastAPI application package."""

__all__ = ["app"]


def __getattr__(name: str):
    """Lazily expose the FastAPI application without import-time side effects."""

    if name == "app":
        from .main import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
