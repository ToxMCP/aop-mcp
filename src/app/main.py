"""FastAPI application entrypoint for the AOP MCP service."""

from fastapi import FastAPI

from src.server.mcp.router import router as mcp_router


def create_app() -> FastAPI:
    """Construct the FastAPI instance with baseline routes."""

    app = FastAPI(
        title="AOP MCP Server",
        description=(
            "Agent-facing API for Adverse Outcome Pathway discovery and authoring"
        ),
        version="0.1.0",
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Return a minimal liveness payload."""

        return {"status": "ok"}

    app.include_router(mcp_router)

    return app


app = create_app()
