"""FastAPI application exposing MCP endpoint."""

from __future__ import annotations

import hmac

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.instrumentation.audit import tool_call_audit_log
from src.server.config.settings import get_settings
from src.server.mcp.router import router as mcp_router
from src.server.version import get_app_version


def _is_allowed_local_origin(origin: str) -> bool:
    return origin.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]"))


def create_app() -> FastAPI:
    settings = get_settings()
    tool_call_audit_log.configure_jsonl_sink(settings.audit_log_path)
    app = FastAPI(
        title="AOP MCP Server",
        description="Model Context Protocol server for Adverse Outcome Pathway tooling",
        version=get_app_version(),
    )

    @app.middleware("http")
    async def mcp_security_boundary(request: Request, call_next):
        if request.url.path != "/mcp":
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Request body too large"}},
            )

        origin = request.headers.get("origin")
        if origin:
            allowed = set(settings.allowed_origins)
            if origin not in allowed and not (not settings.is_production and _is_allowed_local_origin(origin)):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"jsonrpc": "2.0", "error": {"code": -32003, "message": "Origin not allowed"}},
                )

        if settings.auth_mode == "bearer":
            header = request.headers.get("authorization", "")
            expected = f"Bearer {settings.auth_bearer_token}"
            if not hmac.compare_digest(header, expected):
                scopes = " ".join(settings.auth_bearer_scopes)
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    headers={"WWW-Authenticate": f'Bearer scope="{scopes}"'},
                    content={"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized"}},
                )
            request.state.toxmcp_scopes = list(settings.auth_bearer_scopes)
            request.state.toxmcp_enforce_confirmations = True

        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(mcp_router)
    return app


app = create_app()
