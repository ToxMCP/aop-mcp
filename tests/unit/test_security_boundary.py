from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.server.api.server import _is_allowed_local_origin, create_app
from src.server.config.settings import get_settings
from src.server.mcp.protocol import FORBIDDEN


def _clear_settings() -> None:
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost",
        "http://localhost:8003",
        "http://127.0.0.1:3000",
        "http://[::1]",
        "http://[::1]:8003",
    ],
)
def test_development_origin_accepts_exact_loopback_hosts(origin: str) -> None:
    assert _is_allowed_local_origin(origin)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost.evil.example",
        "http://127.0.0.1.evil.example",
        "http://127.0.0.10:9000",
        "http://localhost@evil.example",
        "http://evil.example@localhost",
        "http://[::1]evil.example",
        "http://localhost:70000",
        "http://localhost:invalid",
        "http://localhost:0",
        "http://localhost:",
        "http://localhost/path",
        "http://localhost?",
        "http://localhost#fragment",
        "http://local\nhost",
        " http://localhost",
        "https://localhost",
        "null",
    ],
)
def test_development_origin_rejects_lookalike_and_malformed_origins(origin: str) -> None:
    assert not _is_allowed_local_origin(origin)


@pytest.mark.parametrize("origin", ["http://localhost.evil.example", "http://127.0.0.1.evil.example"])
def test_mcp_rejects_remote_origin_before_processing_simple_post(
    origin: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AOP_MCP_ENVIRONMENT", "development")
    monkeypatch.setenv("AOP_MCP_AUTH_MODE", "disabled")
    monkeypatch.setenv("AOP_MCP_ALLOWED_ORIGINS", "")
    _clear_settings()
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/mcp",
                headers={"origin": origin, "content-type": "text/plain"},
                content='{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}',
            )
        assert response.status_code == 403
        assert response.json()["error"]["message"] == "Origin not allowed"
    finally:
        _clear_settings()


def test_production_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AOP_MCP_ENVIRONMENT", "production")
    monkeypatch.setenv("AOP_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("AOP_MCP_ALLOWED_ORIGINS", "https://agent.example")
    monkeypatch.setenv("AOP_MCP_AUTH_MODE", "disabled")
    _clear_settings()

    with pytest.raises(ValidationError):
        create_app()

    _clear_settings()


def test_mcp_endpoint_requires_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AOP_MCP_ENVIRONMENT", "production")
    monkeypatch.setenv("AOP_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("AOP_MCP_ALLOWED_ORIGINS", "https://agent.example")
    monkeypatch.setenv("AOP_MCP_AUTH_MODE", "bearer")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_TOKEN", "secret-token")
    _clear_settings()

    client = TestClient(create_app())
    response = client.post(
        "/mcp",
        headers={"origin": "https://agent.example"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Unauthorized"
    _clear_settings()


def test_tool_list_exposes_security_annotations() -> None:
    _clear_settings()
    client = TestClient(create_app())
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    assert all("annotations" in tool for tool in tools)
    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["search_aops"]["annotations"]["requiredScopes"] == ["toxmcp:live"]
    assert by_name["export_draft_review_artifact"]["annotations"]["requiresConfirmation"] is True
    assert by_name["export_draft_review_artifact"]["annotations"]["readOnlyHint"] is True
    assert by_name["export_draft_review_artifact"]["annotations"]["openWorldHint"] is True
    assert by_name["review_draft_bundle"]["annotations"]["riskClass"] == "live"
    assert by_name["review_draft_bundle"]["annotations"]["requiredScopes"] == ["toxmcp:live"]
    assert by_name["review_draft_evidence_gaps"]["annotations"]["openWorldHint"] is True
    assert by_name["trace_chemical_on_draft"]["annotations"]["riskClass"] == "live"
    assert by_name["link_stressor"]["annotations"]["riskClass"] == "execute"
    assert by_name["link_stressor"]["annotations"]["requiredScopes"] == ["toxmcp:execute"]
    assert by_name["link_stressor"]["annotations"]["requiresConfirmation"] is True


def test_mcp_endpoint_enforces_bearer_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AOP_MCP_AUTH_MODE", "bearer")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_TOKEN", "secret-token")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_SCOPES", "toxmcp:read")
    _clear_settings()

    client = TestClient(create_app())
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer secret-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_aops",
                "arguments": {"text": "liver", "limit": 1},
            },
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == FORBIDDEN
    assert payload["error"]["data"]["missingScopes"] == ["toxmcp:live"]
    _clear_settings()


def test_mcp_endpoint_enforces_confirmation_for_bearer_write_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AOP_MCP_AUTH_MODE", "bearer")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_TOKEN", "secret-token")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_SCOPES", "toxmcp:read,toxmcp:execute")
    _clear_settings()

    client = TestClient(create_app())
    request_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "create_draft_aop",
            "arguments": {
                "draft_id": "confirmed-scope-draft",
                "title": "PXR activation leading to liver steatosis",
                "description": "Scoped confirmation test.",
                "adverse_outcome": "Liver steatosis",
                "author": "tester",
                "summary": "create draft",
            },
        },
    }

    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer secret-token"},
        json=request_payload,
    )
    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == FORBIDDEN
    assert payload["error"]["data"]["requiresConfirmation"] is True

    confirmed_payload = {
        **request_payload,
        "id": 2,
        "params": {
            **request_payload["params"],
            "confirmed": True,
        },
    }
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer secret-token"},
        json=confirmed_payload,
    )
    assert response.status_code == 200
    structured = response.json()["result"]["structuredContent"]
    assert structured == {"draft_id": "confirmed-scope-draft", "version_id": "v1"}
    _clear_settings()


def test_mcp_endpoint_treats_link_stressor_as_write_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AOP_MCP_AUTH_MODE", "bearer")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_TOKEN", "secret-token")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_SCOPES", "toxmcp:read")
    _clear_settings()

    client = TestClient(create_app())
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer secret-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "link_stressor",
                "arguments": {
                    "draft_id": "draft-id",
                    "version_id": "v1",
                    "author": "tester",
                    "summary": "link stressor",
                    "stressor_id": "stress-1",
                    "label": "Example stressor",
                    "source": "DTXSID000000",
                    "target": "ke-1",
                },
                "confirmed": True,
            },
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == FORBIDDEN
    assert payload["error"]["data"]["missingScopes"] == ["toxmcp:execute"]
    _clear_settings()
