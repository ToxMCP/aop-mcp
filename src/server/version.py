"""Shared application version metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def get_app_version() -> str:
    try:
        return version("aop-mcp-server")
    except PackageNotFoundError:
        return "0.6.0"
