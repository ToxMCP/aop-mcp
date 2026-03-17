"""FastAPI application exposing MCP endpoint."""

from __future__ import annotations

from fastapi import FastAPI

from src.server.config.settings import get_settings
from src.server.mcp.router import router as mcp_router
from src.server.version import get_app_version


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AOP MCP Server",
        description="Model Context Protocol server for Adverse Outcome Pathway tooling",
        version=get_app_version(),
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(mcp_router)
    return app


app = create_app()
