"""Pydantic models for the MCP JSON-RPC protocol."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeatureSupport(BaseModel):
    enabled: bool


class ServerInfo(BaseModel):
    name: str
    version: str


class InitializeClientInfo(BaseModel):
    name: str
    version: Optional[str] = None


class InitializeParams(BaseModel):
    protocolVersion: Optional[str] = None
    client: Optional[InitializeClientInfo] = None
    clientInfo: Optional[InitializeClientInfo] = None  # Some clients use this
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    
    @model_validator(mode='after')
    def use_client_info(self):
        # Accept either client or clientInfo
        if self.clientInfo and not self.client:
            self.client = self.clientInfo
        elif not self.client:
            # Provide a default if neither is present
            self.client = InitializeClientInfo(name="unknown", version=None)
        return self


class InitializeResult(BaseModel):
    protocolVersion: str
    serverInfo: ServerInfo
    capabilities: Dict[str, FeatureSupport]


class ToolInputProperty(BaseModel):
    name: str
    description: str
    required: bool = True


class ToolDescription(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    description: str
    input_schema: Dict[str, Any] = Field(
        alias="inputSchema",
        serialization_alias="inputSchema",
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="outputSchema",
        serialization_alias="outputSchema",
    )


class ListToolsResult(BaseModel):
    tools: List[ToolDescription]


class PromptDescription(BaseModel):
    name: str
    description: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None


class ListPromptsResult(BaseModel):
    prompts: List[PromptDescription]


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
