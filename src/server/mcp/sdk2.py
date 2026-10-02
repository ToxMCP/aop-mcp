"""Stable SDK2 adapter around the existing AOP dispatch and policy boundary."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import anyio
from mcp.server.context import ServerRequestContext
from mcp.server.caching import CacheHint
from mcp.server.lowlevel import Server
from mcp.server.request_state import RequestStateBoundary, RequestStateSecurity
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp_types import (
    CallToolRequestParams, CallToolResult, ErrorData, ListPromptsResult,
    ListToolsResult, PaginatedRequestParams, PROTOCOL_VERSION_META_KEY, Tool,
    ToolAnnotations, InputRequiredResult, ElicitRequest, ElicitRequestFormParams, ElicitResult,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from src.server.config.settings import Settings, get_settings
from src.server.mcp import router as legacy
from src.server.version import get_app_version
from src.server.tools.comparison import CompareAopsInput, context_question, initial_result, missing_context
from pydantic import ValidationError

POLICY_META_KEY = "org.toxmcp/toolPolicy"
CONFIRMATION_META_KEY = "org.toxmcp/confirmation"
LEGACY_HTTP_REVISIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
COMPARISON_QUESTION_ID = "aop-comparison-context-v1"


def _guided_context(params: CallToolRequestParams) -> dict[str, Any] | InputRequiredResult | CallToolResult:
    """Validate answers to exactly the requested fields; never replace supplied context."""
    arguments = dict(params.arguments or {})
    parsed = CompareAopsInput.model_validate(arguments)
    missing = missing_context(parsed)
    if not missing:
        if params.input_responses is not None or params.request_state is not None:
            raise legacy.JSONRPCError(legacy.INVALID_PARAMS, "This comparison does not need resumed input.")
        return arguments
    schema = context_question(parsed)
    state = json.dumps({"question": COMPARISON_QUESTION_ID, "schema": schema}, sort_keys=True)
    if params.input_responses is None:
        if params.request_state is not None:
            raise legacy.JSONRPCError(legacy.INVALID_PARAMS, "Resume with the answer to the context question.")
        return InputRequiredResult(input_requests={COMPARISON_QUESTION_ID: ElicitRequest(
            params=ElicitRequestFormParams(message="Which species and life stage should this AOP comparison consider? Use unspecified if unknown.",
                                         requested_schema=schema))}, request_state=state,
                                   meta={"sources": legacy.tool_registry.get_tool("compare_aops").sources})
    if params.request_state != state or set(params.input_responses) != {COMPARISON_QUESTION_ID}:
        raise legacy.JSONRPCError(legacy.INVALID_PARAMS, "Resume the original context question with its requestState.")
    answer = params.input_responses[COMPARISON_QUESTION_ID]
    if not isinstance(answer, ElicitResult):
        raise legacy.JSONRPCError(legacy.INVALID_PARAMS, "A context form answer is required.")
    if answer.action in {"cancel", "decline"}:
        tool = legacy.tool_registry.get_tool("compare_aops")
        return CallToolResult(content=[{"type": "text", "text": "AOP comparison cancelled." + legacy._render_sources(tool.sources)}],
                              structured_content=initial_result(parsed, "cancelled"), meta={"sources": tool.sources})
    from jsonschema import validate, ValidationError as SchemaError
    try:
        validate(answer.content, schema)
    except SchemaError as error:
        raise legacy.JSONRPCError(legacy.INVALID_PARAMS, "Answer every requested context field using text; extra fields are not accepted.") from error
    return CompareAopsInput.model_validate({**arguments, **answer.content}).model_dump(exclude_none=True)


def _state_principal(context: ServerRequestContext) -> str | None:
    # Auth is enforced by FastAPI rather than the SDK's OAuth middleware.
    if context.request is None:
        return None
    authorization = context.request.headers.get("authorization")
    return hashlib.sha256(authorization.encode()).hexdigest() if authorization else None


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
    ) -> CallToolResult | InputRequiredResult:
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
            arguments = params.arguments or {}
            prepared_result = None
            if params.name == "compare_aops":
                tool = legacy.tool_registry.get_tool(params.name)
                legacy._check_tool_policy(tool, execution_context, confirmed)
                capabilities = context.session.client_capabilities
                supports_form = bool(capabilities and capabilities.elicitation and capabilities.elicitation.form is not None)
                if context.protocol_version not in LEGACY_HTTP_REVISIONS and supports_form:
                    prepared = _guided_context(params)
                    if isinstance(prepared, InputRequiredResult):
                        # Audit the schema-validated pending result without fetching data.
                        await legacy._dispatch_tool_call(params.name, arguments,
                            execution_context=execution_context, confirmed=confirmed)
                        return prepared
                    if isinstance(prepared, CallToolResult):
                        prepared_result = prepared.structured_content
                    else:
                        arguments = prepared
                elif params.input_responses is not None or params.request_state is not None:
                    raise legacy.JSONRPCError(legacy.INVALID_PARAMS, "Pass species and life_stage directly with this client.")
            result = await legacy._dispatch_tool_call(
                params.name, arguments,
                execution_context=execution_context, confirmed=confirmed,
                prepared_result=prepared_result,
            )
        except legacy.JSONRPCError as error:
            raise MCPError.from_error_data(ErrorData(code=error.code, message=error.message, data=error.data)) from error
        except ValidationError as error:
            raise MCPError(code=legacy.INVALID_PARAMS, message=str(error)) from error
        return CallToolResult.model_validate(result)

    server = Server(
        "AOP MCP Server", version=get_app_version(), instructions=legacy.SERVER_INSTRUCTIONS,
        on_list_tools=list_tools, on_call_tool=call_tool, on_list_prompts=list_prompts,
        cache_hints={"tools/list": CacheHint(ttl_ms=60_000, scope="private"),
                     "prompts/list": CacheHint(ttl_ms=60_000, scope="private")},
    )
    settings = get_settings()
    security = (RequestStateSecurity(keys=[settings.request_state_key.get_secret_value()])
                if settings.request_state_key else RequestStateSecurity.ephemeral())
    security.bind_principal = _state_principal
    server.middleware.append(RequestStateBoundary(security, default_audience="AOP MCP Server"))
    return server


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
