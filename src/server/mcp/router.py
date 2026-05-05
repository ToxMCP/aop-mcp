"""FastAPI router implementing MCP JSON-RPC endpoints."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request, Response, status
from pydantic import ValidationError

from src.instrumentation.audit import (
    ToolCallAuditRecord,
    hash_json,
    tool_call_audit_log,
    utc_timestamp,
)
from src.server.mcp.protocol import (
    FeatureSupport,
    InitializeParams,
    InitializeResult,
    JSONRPCError,
    JSONRPCRequest,
    ListPromptsResult,
    ListToolsResult,
    PromptDescription,
    ServerInfo,
    INVALID_PARAMS,
    INVALID_REQUEST,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    FORBIDDEN,
)
from src.server.tools.registry import tool_registry
from src.server.version import get_app_version
from src.tools import SchemaValidationError, validate_payload_against_schema

log = logging.getLogger(__name__)


router = APIRouter()

SERVER_INFO = ServerInfo(name="AOP MCP Server", version=get_app_version())
MCP_VERSION = "2025-03-26"

SERVER_CAPABILITIES: dict[str, FeatureSupport] = {
    "tools": FeatureSupport(enabled=True),
    "prompts": FeatureSupport(enabled=True),  # Enable prompt support
    "resources": FeatureSupport(enabled=False),
}

ALL_TOOL_SCOPES = frozenset(
    {
        "toxmcp:read",
        "toxmcp:live",
        "toxmcp:execute",
        "toxmcp:export",
        "toxmcp:admin",
    }
)


@dataclass(frozen=True)
class ToolExecutionContext:
    scopes: frozenset[str] = ALL_TOOL_SCOPES
    enforce_confirmations: bool = False


def _response(result: Any = None, error: dict | None = None, request_id: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0"}
    if result is not None:
        payload["result"] = result
    if error is not None:
        payload["error"] = error
    if request_id is not None:
        payload["id"] = request_id
    return payload


@router.post("/mcp")
async def mcp_endpoint(request: Request, response: Response):
    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover - FastAPI handles details
        log.error("Failed to parse JSON: %s", exc)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return _response(
            error={"code": PARSE_ERROR, "message": "Invalid JSON"},
            request_id=None,
        )

    if not isinstance(payload, dict):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return _response(
            error={"code": INVALID_REQUEST, "message": "Request body must be a JSON object"},
            request_id=None,
        )

    try:
        rpc_request = JSONRPCRequest.model_validate(payload)
        log.debug("Received MCP request: method=%s, id=%s", rpc_request.method, rpc_request.id)
    except ValidationError as exc:
        log.error("Invalid JSON-RPC request: %s", exc)
        response.status_code = status.HTTP_400_BAD_REQUEST
        return _response(
            error={"code": INVALID_REQUEST, "message": str(exc)},
            request_id=payload.get("id"),
        )

    try:
        result = await dispatch_request(
            rpc_request,
            execution_context=_execution_context_from_request(request),
        )
    except JSONRPCError as exc:
        log.error("MCP JSON-RPC error: code=%s, message=%s, data=%s", exc.code, exc.message, exc.data)
        status_code = status.HTTP_200_OK
        if exc.code == INVALID_PARAMS:
            status_code = status.HTTP_400_BAD_REQUEST
        elif exc.code == METHOD_NOT_FOUND:
            status_code = status.HTTP_404_NOT_FOUND
        elif exc.code == FORBIDDEN:
            status_code = status.HTTP_403_FORBIDDEN
        elif exc.code == INTERNAL_ERROR:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        response.status_code = status_code
        error_payload = {"code": exc.code, "message": exc.message}
        if exc.data is not None:
            error_payload["data"] = exc.data
        return _response(error=error_payload, request_id=rpc_request.id)
    except Exception as exc:  # pragma: no cover - safeguard
        log.exception("Unhandled MCP error during dispatch")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return _response(
            error={"code": INTERNAL_ERROR, "message": "Internal server error"},
            request_id=rpc_request.id,
        )

    # Handle notifications (no ID) - these don't expect a response
    if rpc_request.id is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return {}
    
    # For requests with an ID, return the result
    return _response(result=result, request_id=rpc_request.id)


async def dispatch_request(
    request: JSONRPCRequest,
    *,
    execution_context: ToolExecutionContext | None = None,
) -> Any:
    context = execution_context or ToolExecutionContext()
    log.debug("Dispatching MCP method: %s", request.method)
    if request.method == "initialize":
        InitializeParams.model_validate(request.params or {})
        return InitializeResult(
            protocolVersion=MCP_VERSION,
            serverInfo=SERVER_INFO,
            capabilities=SERVER_CAPABILITIES,
        ).model_dump(by_alias=True)

    if request.method in {"initialized", "notifications/initialized"}:
        # Return empty object for initialized notification
        return {}
    
    if request.method in {"shutdown", "exit", "notifications/shutdown"}:
        return {}

    if request.method in {"tools/list", "mcp/tool/list"}:
        tools = tool_registry.list_tools()
        return ListToolsResult(tools=tools).model_dump(by_alias=True, exclude_none=True)

    if request.method in {"prompts/list", "mcp/prompt/list"}:
        # Return an empty list of prompts for now to satisfy the client
        return ListPromptsResult(prompts=[]).model_dump(by_alias=True, exclude_none=True)

    if request.method in {"tools/call", "mcp/tool/call"}:
        if not isinstance(request.params, dict):
            raise JSONRPCError(INVALID_PARAMS, "Params must be an object")
        name = request.params.get("name")
        arguments = request.params.get("arguments") or {}
        argument_keys = sorted(arguments) if isinstance(arguments, dict) else []
        log.debug("Calling tool: name=%s, argument_keys=%s", name, argument_keys)
        if not isinstance(name, str):
            raise JSONRPCError(INVALID_PARAMS, "Missing tool name")
        if not isinstance(arguments, dict):
            raise JSONRPCError(INVALID_PARAMS, "Tool arguments must be an object")
        return await _dispatch_tool_call(
            name,
            arguments,
            execution_context=context,
            confirmed=_tool_call_confirmed(request.params),
        )

    log.error("Method not found: %s", request.method)
    raise JSONRPCError(METHOD_NOT_FOUND, f"Method not found: {request.method}")


def _execution_context_from_request(request: Request) -> ToolExecutionContext:
    scopes = getattr(request.state, "toxmcp_scopes", None)
    enforce_confirmations = bool(
        getattr(request.state, "toxmcp_enforce_confirmations", False)
    )
    if scopes is None:
        return ToolExecutionContext()
    return ToolExecutionContext(
        scopes=frozenset(str(scope) for scope in scopes),
        enforce_confirmations=enforce_confirmations,
    )


def _tool_call_confirmed(params: dict[str, Any]) -> bool:
    if params.get("confirmed") is True or params.get("confirm") is True:
        return True
    confirmation = params.get("confirmation")
    return isinstance(confirmation, dict) and confirmation.get("confirmed") is True


async def _dispatch_tool_call(
    name: str,
    arguments: dict[str, Any],
    *,
    execution_context: ToolExecutionContext,
    confirmed: bool,
) -> dict[str, Any]:
    call_id = str(uuid4())
    started_at = utc_timestamp()
    start = perf_counter()
    tool_def = None
    result: Any | None = None
    status_value = "error"
    output_validation_status = "not_applicable"
    policy_status = "not_evaluated"
    error_type: str | None = None
    error_message: str | None = None

    try:
        tool_def = tool_registry.get_tool(name)
        missing_scopes = sorted(
            set(tool_def.required_scopes) - set(execution_context.scopes)
        )
        if missing_scopes:
            policy_status = "failed"
            raise JSONRPCError(
                FORBIDDEN,
                "Missing required tool scope(s): " + ", ".join(missing_scopes),
                data={
                    "requiredScopes": list(tool_def.required_scopes),
                    "grantedScopes": sorted(execution_context.scopes),
                    "missingScopes": missing_scopes,
                },
            )
        if (
            tool_def.requires_confirmation
            and execution_context.enforce_confirmations
            and not confirmed
        ):
            policy_status = "failed"
            raise JSONRPCError(
                FORBIDDEN,
                "Tool requires explicit confirmation",
                data={
                    "requiresConfirmation": True,
                    "riskClass": tool_def.risk_class,
                },
            )
        policy_status = "passed"
        result = await tool_registry.call_tool(name, arguments)
        if tool_def.output_schema:
            validate_payload_against_schema(result, tool_def.output_schema)
            output_validation_status = "passed"

        response = {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
        }
        if tool_def.output_schema:
            response["structuredContent"] = result
        status_value = "success"
        return response
    except KeyError:
        error_type = "KeyError"
        error_message = f"Tool not found: {name}"
        log.error("%s", error_message)
        raise JSONRPCError(METHOD_NOT_FOUND, error_message)
    except ValidationError as exc:
        error_type = "ValidationError"
        error_message = str(exc)
        log.error("Invalid params for tool %s: %s", name, exc)
        raise JSONRPCError(INVALID_PARAMS, str(exc))
    except SchemaValidationError as exc:
        output_validation_status = "failed"
        error_type = "SchemaValidationError"
        error_message = str(exc)
        log.error("Tool output failed schema validation for %s: %s", name, exc)
        raise JSONRPCError(
            INTERNAL_ERROR,
            "Tool output failed schema validation",
            data={"errorType": "SchemaValidationError"},
        )
    except JSONRPCError as exc:
        error_type = "JSONRPCError"
        error_message = exc.message
        raise
    except Exception as exc:
        error_type = type(exc).__name__
        error_message = str(exc)
        log.exception("Tool execution failed for %s", name)
        raise JSONRPCError(
            INTERNAL_ERROR,
            "Tool execution failed",
            data={"errorType": type(exc).__name__},
        )
    finally:
        finished_at = utc_timestamp()
        output_schema = tool_def.output_schema if tool_def is not None else None
        audit_record = ToolCallAuditRecord(
            call_id=call_id,
            tool_name=name,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=round((perf_counter() - start) * 1000, 3),
            status=status_value,
            argument_keys=sorted(arguments),
            request_hash=hash_json({"tool": name, "arguments": arguments}),
            response_hash=hash_json(result) if result is not None else None,
            output_schema_title=output_schema.get("title") if output_schema else None,
            output_schema_hash=hash_json(output_schema) if output_schema else None,
            output_validation_status=output_validation_status,
            risk_class=tool_def.risk_class if tool_def is not None else None,
            required_scopes=list(tool_def.required_scopes) if tool_def is not None else [],
            granted_scopes=sorted(execution_context.scopes),
            requires_confirmation=tool_def.requires_confirmation if tool_def is not None else None,
            confirmation_provided=confirmed,
            policy_status=policy_status,
            error_type=error_type,
            error_message=error_message,
        )
        tool_call_audit_log.append(audit_record)
