"""Pydantic models for the MCP JSON-RPC protocol."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FeatureSupport(BaseModel):
    enabled: bool


class ServerInfo(BaseModel):
    name: str
    version: str


class InitializeClientInfo(BaseModel):
    name: str
    version: Optional[str] = None


class InitializeParams(BaseModel):
    client: InitializeClientInfo
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class InitializeResult(BaseModel):
    server: ServerInfo
    capabilities: Dict[str, FeatureSupport]


class ToolInputProperty(BaseModel):
    name: str
    description: str
    required: bool = True


class ToolDescription(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None


class ListToolsResult(BaseModel):
    tools: List[ToolDescription]


class JSONRPCRequest(BaseModel):
    jsonrpc: str
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None


class JSONRPCError(Exception):
    def __init__(self, code: int, message: str, data: Any | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# Error codes from specification
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

UNAUTHORIZED = -32001
FORBIDDEN = -32003
TOOL_EXECUTION_ERROR = -32010

