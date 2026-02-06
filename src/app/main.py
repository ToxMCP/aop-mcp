"""Compatibility entrypoint for environments importing src.app.main."""

from src.server.api.server import app, create_app

__all__ = ["app", "create_app"]
