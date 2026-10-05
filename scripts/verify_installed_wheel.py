"""Exercise the installed wheel with Python -I from outside the source checkout."""

from __future__ import annotations

import os
from pathlib import Path

os.environ["AOP_MCP_ENABLE_FIXTURE_FALLBACK"] = "1"
os.environ["AOP_MCP_ENVIRONMENT"] = "test"
os.environ["AOP_MCP_AUTH_MODE"] = "disabled"

from fastapi.testclient import TestClient

import src
from src.adapters.sparql_client import SparqlClient, SparqlUpstreamError
from src.server.api.server import app
from src.server.tools.aop import _schema_contract_manifest
from src.tools import load_schema, validate_payload


def main() -> None:
    source_root = Path(__file__).resolve().parents[1]
    assert not Path(src.__file__).resolve().is_relative_to(source_root), "Imported the checkout, not the wheel"
    manifest = _schema_contract_manifest()
    assert manifest["schema_count"] > 0
    assert len(manifest["tracked_response_schemas"]) == 4
    assert load_schema("read", "search_aops.response.schema")["title"] == "search_aops.response"

    # Force the adapter's real offline path, exercising installed templates and fixtures.
    async def unavailable(*args, **kwargs):
        raise SparqlUpstreamError("Installed-wheel offline smoke")

    SparqlClient.query = unavailable
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        initialized = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert initialized.status_code == 200, initialized.text
        assert initialized.json()["result"]["serverInfo"]["name"] == "AOP MCP Server"
        listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert listed.status_code == 200, listed.text
        tools = listed.json()["result"]["tools"]
        assert {"search_aops", "assess_aop_confidence"} <= {tool["name"] for tool in tools}
        assert all(tool["outputSchema"] for tool in tools)
        searched = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "search_aops", "arguments": {"text": "liver", "limit": 1}},
        })
        assert searched.status_code == 200, searched.text
        payload = searched.json()["result"]["structuredContent"]
        assert payload["results"], "Bundled offline fixture was not loaded"
        validate_payload(payload, namespace="read", name="search_aops.response.schema")
    print(f"Installed-wheel MCP smoke passed: {len(tools)} tools, {manifest['schema_count']} schemas")


if __name__ == "__main__":
    main()
