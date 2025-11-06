from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.server.api.server import app


client = TestClient(app)


def _call_rpc(method: str, *, params: dict | None = None, request_id: int = 1) -> TestClient:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    response = client.post("/mcp", json=payload)
    return response


def test_initialize_success() -> None:
    response = _call_rpc("initialize", params={"client": {"name": "test", "version": "1.0"}, "capabilities": {}})
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["serverInfo"]["name"] == "AOP MCP Server"


def test_initialized_returns_empty_object_response() -> None:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "initialized",
        },
    )
    assert response.status_code == 204
    assert response.content == b""


def test_tools_list_includes_registered_tools() -> None:
    response = _call_rpc("tools/list", params={})
    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    tool_names = {tool["name"] for tool in tools}
    assert {"search_aops", "get_aop", "create_draft_aop"}.issubset(tool_names)


@pytest.mark.skip(reason="Requires live SPARQL endpoints; enable in environments with network access")
def test_tools_call_search_aops_live() -> None:
    response = _call_rpc(
        "tools/call",
        params={
            "name": "search_aops",
            "arguments": {"text": "liver", "limit": 1},
        },
    )
    assert response.status_code == 200
    payload = response.json()["result"]["content"][0]["data"]
    assert "results" in payload


def test_tools_call_search_aops_with_golden_fixture(monkeypatch) -> None:
    from src.adapters import SparqlClient

    fixture = {
        "results": {
            "bindings": [
                {
                    "aop": {"value": "http://aopwiki.org/aops/123"},
                    "title": {"value": "Example"},
                    "shortName": {"value": "AOP123"},
                }
            ]
        }
    }

    async def fake_query(self, query: str, **kwargs):  # type: ignore[no-untyped-def]
        return fixture

    monkeypatch.setattr(SparqlClient, "query", fake_query)
    response = _call_rpc(
        "tools/call",
        params={
            "name": "search_aops",
            "arguments": {"text": "liver", "limit": 1},
        },
    )
    assert response.status_code == 200
    payload = response.json()["result"]
    content = payload["content"][0]
    assert content["type"] == "text"
    structured = payload["structuredContent"]
    assert structured["results"][0]["id"] == "AOP:123"


def test_tools_call_returns_error_for_unknown_tool() -> None:
    response = _call_rpc("tools/call", params={"name": "nope", "arguments": {}})
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == -32601  # METHOD_NOT_FOUND
