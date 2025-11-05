from __future__ import annotations

from fastapi.testclient import TestClient

from src.server.api.server import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_list_tools_via_mcp() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    tools = data["result"]["tools"]
    assert any(tool["name"] == "search_aops" for tool in tools)

