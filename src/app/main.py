"""FastAPI application entrypoint for the Taskmaster MCP service."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Construct the FastAPI instance with baseline routes."""

    app = FastAPI(
        title="Taskmaster MCP",
        description=(
            "Agent-facing API for Adverse Outcome Pathway discovery and authoring"
        ),
        version="0.1.0",
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Return a minimal liveness payload."""

        return {"status": "ok"}

    return app


app = create_app()
