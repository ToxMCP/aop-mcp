"""FastAPI application exposing MCP endpoint."""

from __future__ import annotations

from fastapi import FastAPI

from src.server.config.settings import get_settings
from src.server.mcp.router import router as mcp_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AOP MCP Server",
        description="Model Context Protocol server for Adverse Outcome Pathway tooling",
        version="0.1.0",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(mcp_router)
    return app


app = create_app()

