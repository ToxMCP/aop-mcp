"""FastAPI application exposing MCP endpoint."""

from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.instrumentation.audit import tool_call_audit_log
from src.server.config.settings import get_settings
from src.server.mcp.router import router as mcp_router
from src.server.mcp.sdk2 import create_sdk_http_app
from src.server.mcp.body_limit import MCPBodyLimitMiddleware
from src.server.version import get_app_version


def _is_allowed_local_origin(origin: str) -> bool:
    """Accept serialized HTTP origins for the exact development loopback hosts."""
    if any(character.isspace() for character in origin):
        return False
    try:
        parsed = urlsplit(origin)
        port = parsed.port  # Reject malformed or out-of-range ports.
        hostname = parsed.hostname
    except ValueError:
        return False
    if (
        parsed.scheme != "http"
        or hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or origin != f"{parsed.scheme}://{parsed.netloc}"
        or (port is not None and port < 1)
    ):
        return False
    host = "[::1]" if hostname == "::1" else hostname
    authority = f"{host}:{port}" if port is not None else host
    return parsed.netloc.lower() == authority


def create_app() -> FastAPI:
    settings = get_settings()
    tool_call_audit_log.configure_jsonl_sink(settings.audit_log_path)
    sdk_app = create_sdk_http_app(settings)

    @asynccontextmanager
    async def lifespan(app):
        async with sdk_app.router.lifespan_context(sdk_app):
            yield

    app = FastAPI(
        lifespan=lifespan,
        title="AOP MCP Server",
        description="Model Context Protocol server for Adverse Outcome Pathway tooling",
        version=get_app_version(),
    )

    app.state.sdk2_app = sdk_app

    @app.middleware("http")
    async def mcp_security_boundary(request: Request, call_next):
        if request.url.path != "/mcp":
            return await call_next(request)

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

    app.add_middleware(MCPBodyLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.include_router(mcp_router)
    return app


app = create_app()
