from __future__ import annotations

from typing import Any

import pytest

from src.instrumentation.audit import tool_call_audit_log
from src.server.mcp import router as router_module
from src.server.mcp.protocol import FORBIDDEN, INTERNAL_ERROR, JSONRPCError, JSONRPCRequest


class FakeRegisteredTool:
    output_schema = {
        "title": "fake_tool.response",
        "type": "object",
        "required": ["ok"],
        "properties": {"ok": {"type": "boolean"}},
        "additionalProperties": False,
    }
    risk_class = "read"
    required_scopes = ("toxmcp:read",)
    requires_confirmation = False


class FakeToolRegistry:
    def __init__(
        self,
        result: dict[str, Any],
        *,
        required_scopes: tuple[str, ...] = ("toxmcp:read",),
        requires_confirmation: bool = False,
    ) -> None:
        self._result = result
        self._tool = FakeRegisteredTool()
        self._tool.required_scopes = required_scopes
        self._tool.requires_confirmation = requires_confirmation

    def get_tool(self, name: str) -> FakeRegisteredTool:
        if name != "fake_tool":
            raise KeyError(f"Tool '{name}' not found")
        return self._tool

    async def call_tool(self, name: str, params: dict[str, Any] | None) -> dict[str, Any]:
        self.get_tool(name)
        return dict(self._result)


@pytest.fixture(autouse=True)
def clear_tool_audit_log() -> None:
    tool_call_audit_log.clear()
    yield
    tool_call_audit_log.clear()


@pytest.mark.asyncio
async def test_tool_call_audit_records_success_and_schema_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(router_module, "tool_registry", FakeToolRegistry({"ok": True}))

    response = await router_module.dispatch_request(
        JSONRPCRequest(
            jsonrpc="2.0",
            id=1,
            method="tools/call",
            params={"name": "fake_tool", "arguments": {"alpha": 1}},
        )
    )

    assert response["structuredContent"] == {"ok": True}
    records = tool_call_audit_log.list_records()
    assert len(records) == 1
    record = records[0]
    assert record.tool_name == "fake_tool"
    assert record.status == "success"
    assert record.argument_keys == ["alpha"]
    assert record.output_schema_title == "fake_tool.response"
    assert record.output_validation_status == "passed"
    assert record.risk_class == "read"
    assert record.required_scopes == ["toxmcp:read"]
    assert "toxmcp:read" in record.granted_scopes
    assert record.confirmation_provided is False
    assert record.policy_status == "passed"
    assert record.request_hash
    assert record.response_hash
    assert record.output_schema_hash
    assert record.error_type is None


@pytest.mark.asyncio
async def test_tool_call_audit_records_schema_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(router_module, "tool_registry", FakeToolRegistry({"wrong": True}))

    with pytest.raises(JSONRPCError) as exc_info:
        await router_module.dispatch_request(
            JSONRPCRequest(
                jsonrpc="2.0",
                id=1,
                method="tools/call",
                params={"name": "fake_tool", "arguments": {"alpha": 1}},
            )
        )

    assert exc_info.value.code == INTERNAL_ERROR
    assert exc_info.value.data == {"errorType": "SchemaValidationError"}
    records = tool_call_audit_log.list_records()
    assert len(records) == 1
    record = records[0]
    assert record.tool_name == "fake_tool"
    assert record.status == "error"
    assert record.output_validation_status == "failed"
    assert record.output_schema_title == "fake_tool.response"
    assert record.response_hash
    assert record.error_type == "SchemaValidationError"
    assert record.policy_status == "passed"


@pytest.mark.asyncio
async def test_tool_call_audit_records_scope_policy_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        router_module,
        "tool_registry",
        FakeToolRegistry({"ok": True}, required_scopes=("toxmcp:live",)),
    )

    with pytest.raises(JSONRPCError) as exc_info:
        await router_module.dispatch_request(
            JSONRPCRequest(
                jsonrpc="2.0",
                id=1,
                method="tools/call",
                params={"name": "fake_tool", "arguments": {"alpha": 1}},
            ),
            execution_context=router_module.ToolExecutionContext(
                scopes=frozenset({"toxmcp:read"}),
                enforce_confirmations=True,
            ),
        )

    assert exc_info.value.code == FORBIDDEN
    assert exc_info.value.data["missingScopes"] == ["toxmcp:live"]
    records = tool_call_audit_log.list_records()
    assert len(records) == 1
    record = records[0]
    assert record.status == "error"
    assert record.policy_status == "failed"
    assert record.required_scopes == ["toxmcp:live"]
    assert record.granted_scopes == ["toxmcp:read"]
    assert record.response_hash is None
