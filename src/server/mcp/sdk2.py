"""Stable SDK2 adapter around the existing AOP dispatch and policy boundary."""
from __future__ import annotations

from typing import Any

import anyio
from mcp.server.context import ServerRequestContext
from mcp.server.caching import CacheHint
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp_types import (
    CallToolRequestParams, CallToolResult, ErrorData, ListPromptsResult,
    ListToolsResult, PaginatedRequestParams, PROTOCOL_VERSION_META_KEY, Tool,
    ToolAnnotations,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from src.server.config.settings import Settings, get_settings
from src.server.mcp import router as legacy
from src.server.version import get_app_version

POLICY_META_KEY = "org.toxmcp/toolPolicy"
CONFIRMATION_META_KEY = "org.toxmcp/confirmation"
LEGACY_HTTP_REVISIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}


def is_modern_request(request: Request, payload: dict[str, Any]) -> bool:
    """SDK2 owns claimed modern revisions, including invalid/unsupported claims."""
    revision = request.headers.get("mcp-protocol-version")
    if revision and revision not in LEGACY_HTTP_REVISIONS:
        return True
    params = payload.get("params")
    metadata = params.get("_meta") if isinstance(params, dict) else None
    return isinstance(metadata, dict) and PROTOCOL_VERSION_META_KEY in metadata


def create_sdk_server() -> Server:
    async def list_tools(
        context: ServerRequestContext, params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        tools = []
        for item in legacy.tool_registry.list_tools():
            policy = {key: value for key, value in item.annotations.items()
                      if key in {"riskClass", "requiredScopes", "requiresConfirmation", "sources"}}
            tools.append(Tool(
                name=item.name, description=item.description,
                input_schema=item.input_schema, output_schema=item.output_schema,
                annotations=ToolAnnotations.model_validate(item.annotations),
                meta={POLICY_META_KEY: policy},
            ))
        return ListToolsResult(tools=tools)

    async def list_prompts(
        context: ServerRequestContext, params: PaginatedRequestParams | None,
    ) -> ListPromptsResult:
        return ListPromptsResult(prompts=[])

    async def call_tool(
        context: ServerRequestContext, params: CallToolRequestParams,
    ) -> CallToolResult:
        if context.request is None:
            execution_context = legacy.ToolExecutionContext()
        else:
            # The outer FastAPI bearer boundary populates this request's state.
            execution_context = legacy._execution_context_from_request(context.request)
        raw = dict(context.params or {})
        confirmed = legacy._tool_call_confirmed(raw)
        metadata = raw.get("_meta")
        if isinstance(metadata, dict):
            confirmation = metadata.get(CONFIRMATION_META_KEY)
            confirmed = confirmed or (isinstance(confirmation, dict) and confirmation.get("confirmed") is True)
        try:
            result = await legacy._dispatch_tool_call(
                params.name, params.arguments or {},
                execution_context=execution_context, confirmed=confirmed,
            )
        except legacy.JSONRPCError as error:
            raise MCPError.from_error_data(ErrorData(code=error.code, message=error.message, data=error.data)) from error
        return CallToolResult.model_validate(result)

    return Server(
        "AOP MCP Server", version=get_app_version(), instructions=legacy.SERVER_INSTRUCTIONS,
        on_list_tools=list_tools, on_call_tool=call_tool, on_list_prompts=list_prompts,
        cache_hints={"tools/list": CacheHint(ttl_ms=60_000, scope="private"),
                     "prompts/list": CacheHint(ttl_ms=60_000, scope="private")},
    )


def create_sdk_http_app(settings: Settings):
    allowed_hosts = settings.allowed_hosts or ["localhost:*", "127.0.0.1:*", "[::1]:*"]
    allowed_origins = settings.allowed_origins or ["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"]
    return create_sdk_server().streamable_http_app(
        json_response=True, stateless_http=True, max_request_body_size=settings.max_request_bytes,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts, allowed_origins=allowed_origins,
        ),
    )


class SDKResponse(Response):
    """Delegate the already bounded body to the SDK without re-reading the socket."""
    def __init__(self, application: ASGIApp, body: bytes):
        super().__init__()
        self.application = application
        self.body = body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        supplied = False

        async def replay():
            nonlocal supplied
            if not supplied:
                supplied = True
                return {"type": "http.request", "body": self.body, "more_body": False}
            return await receive()

        await self.application(scope, replay, send)


async def serve_stdio() -> None:
    from src.instrumentation.audit import tool_call_audit_log
    tool_call_audit_log.configure_jsonl_sink(get_settings().audit_log_path)
    server = create_sdk_server()
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def main() -> None:
    anyio.run(serve_stdio)


if __name__ == "__main__":
    main()
