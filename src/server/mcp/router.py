"""FastAPI router implementing MCP JSON-RPC endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Response, status
from pydantic import ValidationError

from src.server.config.settings import get_settings
from src.server.mcp.protocol import (
    FeatureSupport,
    InitializeParams,
    InitializeResult,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    ListToolsResult,
    ServerInfo,
    INVALID_PARAMS,
    INVALID_REQUEST,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)
from src.server.tools.registry import tool_registry

log = logging.getLogger(__name__)


router = APIRouter()

SERVER_INFO = ServerInfo(name="AOP MCP Server", version="0.1.0")
MCP_VERSION = "2025-03-26"

SERVER_CAPABILITIES: dict[str, FeatureSupport] = {
    "tools": FeatureSupport(enabled=True),
    "prompts": FeatureSupport(enabled=False),
    "resources": FeatureSupport(enabled=False),
}


def _response(result: Any = None, error: dict | None = None, request_id: Any | None = None) -> JSONRPCResponse:
    return JSONRPCResponse(jsonrpc="2.0", result=result, error=error, id=request_id)


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
    except ValidationError as exc:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return _response(
            error={"code": INVALID_REQUEST, "message": str(exc)},
            request_id=payload.get("id"),
        )

    try:
        result = await dispatch_request(rpc_request)
    except JSONRPCError as exc:
        status_code = status.HTTP_200_OK
        if exc.code == INVALID_PARAMS:
            status_code = status.HTTP_400_BAD_REQUEST
        elif exc.code == METHOD_NOT_FOUND:
            status_code = status.HTTP_404_NOT_FOUND
        elif exc.code == INTERNAL_ERROR:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        response.status_code = status_code
        return _response(
            error={"code": exc.code, "message": exc.message, "data": exc.data},
            request_id=rpc_request.id,
        )
    except Exception as exc:  # pragma: no cover - safeguard
        log.exception("Unhandled MCP error")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return _response(
            error={"code": INTERNAL_ERROR, "message": str(exc)},
            request_id=rpc_request.id,
        )

    if rpc_request.id is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return _response(result=result, request_id=rpc_request.id)


async def dispatch_request(request: JSONRPCRequest) -> Any:
    if request.method == "initialize":
        InitializeParams.model_validate(request.params or {})
        return InitializeResult(server=SERVER_INFO, capabilities=SERVER_CAPABILITIES).model_dump()

    if request.method in {"initialized", "shutdown", "exit"}:
        return None

    if request.method in {"tools/list", "mcp/tool/list"}:
        tools = tool_registry.list_tools()
        return ListToolsResult(tools=tools).model_dump()

    if request.method in {"tools/call", "mcp/tool/call"}:
        if not isinstance(request.params, dict):
            raise JSONRPCError(INVALID_PARAMS, "Params must be an object")
        name = request.params.get("name")
        arguments = request.params.get("arguments") or {}
        if not isinstance(name, str):
            raise JSONRPCError(INVALID_PARAMS, "Missing tool name")
        try:
            result = await tool_registry.call_tool(name, arguments)
            return {"content": [{"type": "json", "data": result}]}
        except KeyError:
            raise JSONRPCError(METHOD_NOT_FOUND, f"Tool not found: {name}")
        except ValidationError as exc:
            raise JSONRPCError(INVALID_PARAMS, str(exc))
        except Exception as exc:
            raise JSONRPCError(INTERNAL_ERROR, "Tool execution failed", data=str(exc))

    raise JSONRPCError(METHOD_NOT_FOUND, f"Method not found: {request.method}")
