from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.server.api.server import app
from src.server.version import get_app_version


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
    assert data["result"]["serverInfo"]["version"] == get_app_version()


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
    assert {
        "search_aops",
        "get_aop",
        "get_key_event",
        "get_ker",
        "get_related_aops",
        "assess_aop_confidence",
        "find_paths_between_events",
        "map_assay_to_aops",
        "get_assays_for_aop",
        "discover_orphan_stressors_for_aop",
        "discover_orphan_stressors_for_aops",
        "get_assays_for_aops",
        "discover_orphan_stressors_for_query",
        "export_draft_review_artifact",
        "export_draft_replay_package",
        "list_saved_draft_review_artifacts",
        "plan_linear_draft_review_document",
        "review_draft_evidence_gaps",
        "review_registry_handoff_bundle",
        "save_draft_review_artifact",
        "search_assays_for_key_event",
        "trace_chemical_on_draft",
        "review_draft_assay_cutoff_ordering",
        "review_draft_bundle",
        "validate_draft_oecd",
        "verify_tool_call_audit_log",
        "create_draft_aop",
        "attach_registry_handoff_to_draft",
    }.issubset(tool_names)

    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["get_key_event"]["outputSchema"]["title"] == "get_key_event.response"
    assert by_name["get_ker"]["outputSchema"]["title"] == "get_ker.response"
    assert by_name["assess_aop_confidence"]["outputSchema"]["title"] == "assess_aop_confidence.response"
    assert by_name["get_assays_for_aop"]["outputSchema"]["title"] == "list_assays_for_aop.response"
    assert by_name["discover_orphan_stressors_for_aop"]["outputSchema"]["title"] == "discover_orphan_stressors_for_aop.response"
    assert by_name["discover_orphan_stressors_for_aops"]["outputSchema"]["title"] == "discover_orphan_stressors_for_aops.response"
    assert by_name["get_assays_for_aops"]["outputSchema"]["title"] == "list_assays_for_aops.response"
    assert by_name["discover_orphan_stressors_for_query"]["outputSchema"]["title"] == "discover_orphan_stressors_for_query.response"
    assert by_name["export_draft_review_artifact"]["outputSchema"]["title"] == "export_draft_review_artifact.response"
    assert by_name["export_draft_replay_package"]["outputSchema"]["title"] == "export_draft_replay_package.response"
    assert by_name["list_saved_draft_review_artifacts"]["outputSchema"]["title"] == "list_saved_draft_review_artifacts.response"
    assert by_name["plan_linear_draft_review_document"]["outputSchema"]["title"] == "plan_linear_draft_review_document.response"
    assert by_name["review_draft_evidence_gaps"]["outputSchema"]["title"] == "review_draft_evidence_gaps.response"
    assert by_name["review_registry_handoff_bundle"]["outputSchema"]["title"] == "review_registry_handoff_bundle.response"
    assert by_name["save_draft_review_artifact"]["outputSchema"]["title"] == "save_draft_review_artifact.response"
    assert by_name["trace_chemical_on_draft"]["outputSchema"]["title"] == "trace_chemical_on_draft.response"
    assert by_name["review_draft_assay_cutoff_ordering"]["outputSchema"]["title"] == "review_draft_assay_cutoff_ordering.response"
    assert by_name["review_draft_bundle"]["outputSchema"]["title"] == "review_draft_bundle.response"
    assert by_name["attach_registry_handoff_to_draft"]["outputSchema"]["title"] == "update_draft.response"
    assert by_name["verify_tool_call_audit_log"]["outputSchema"]["title"] == "verify_tool_call_audit_log.response"
    assert by_name["verify_tool_call_audit_log"]["annotations"]["riskClass"] == "read"
    assert all("title" in tool["outputSchema"] for tool in tools)
    assert by_name["map_assay_to_aops"]["description"].startswith(
        "Given an assay identifier, return related AOPs. Do not pass AOP IDs."
    )
    assert "Given one AOP identifier" in by_name["get_assays_for_aop"]["description"]
    assert "strongest assay candidates" in by_name["discover_orphan_stressors_for_aop"]["description"]
    assert "cross-AOP support" in by_name["discover_orphan_stressors_for_aops"]["description"]
    assert "phenotype or mechanism query" in by_name["discover_orphan_stressors_for_query"]["description"]
    assert "deterministic replay package" in by_name["export_draft_replay_package"]["description"]
    assert "audit JSONL hash chain" in by_name["verify_tool_call_audit_log"]["description"]
    assert "saved local draft review artifacts" in by_name["list_saved_draft_review_artifacts"]["description"]
    assert "Linear document payload" in by_name["plan_linear_draft_review_document"]["description"]
    assert "concrete evidence gaps" in by_name["review_draft_evidence_gaps"]["description"]
    assert "local artifact output directory" in by_name["save_draft_review_artifact"]["description"]
    assert "Given multiple AOP identifiers" in by_name["get_assays_for_aops"]["description"]
    add_ke_schema = by_name["add_or_update_ke"]["inputSchema"]
    assert add_ke_schema["properties"]["event_role"]["anyOf"][0]["enum"] == [
        "mie",
        "intermediate",
        "ao",
    ]
    essentiality_ref = add_ke_schema["$defs"]["KeyEventAttributesInputModel"]["properties"]["essentiality"]["anyOf"][0]["$ref"]
    essentiality_schema = add_ke_schema["$defs"][essentiality_ref.split("/")[-1]]
    assert "evidence_call" in essentiality_schema["properties"]
    assert essentiality_schema["properties"]["evidence_call"]["enum"] == [
        "high",
        "moderate",
        "low",
        "not_reported",
        "not_assessed",
    ]
    assert by_name["validate_draft_oecd"]["outputSchema"]["title"] == "validate_draft_oecd.response"


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


def test_tools_call_map_assay_to_aops_rejects_explicit_aop_curie() -> None:
    response = _call_rpc(
        "tools/call",
        params={
            "name": "map_assay_to_aops",
            "arguments": {"assay_id": "AOP:34"},
        },
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == -32602
    assert "get_assays_for_aop" in data["error"]["message"]


def test_tools_call_map_assay_to_aops_rejects_explicit_aop_iri() -> None:
    response = _call_rpc(
        "tools/call",
        params={
            "name": "map_assay_to_aops",
            "arguments": {"assay_id": "https://identifiers.org/aop/34"},
        },
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == -32602
    assert "get_assays_for_aops" in data["error"]["message"]


def test_tools_call_add_or_update_ke_accepts_governed_essentiality_and_validator_reports_coverage() -> None:
    draft_id = "mcp-essentiality-pass"
    response = _call_rpc(
        "tools/call",
        params={
            "name": "create_draft_aop",
            "arguments": {
                "draft_id": draft_id,
                "title": "PXR activation leading to liver steatosis",
                "description": "MCP smoke draft.",
                "adverse_outcome": "Liver steatosis",
                "applicability": {"species": "human", "life_stage": "adult", "sex": "female"},
                "references": [{"title": "Example reference"}],
                "author": "tester",
                "summary": "create draft",
            },
        },
    )
    assert response.status_code == 200

    for version_id, identifier, title, attributes in [
        (
            "v2",
            "KE:1",
            "PXR activation",
            {
                "measurement_methods": ["Reporter assay"],
                "essentiality": {
                    "evidence_call": "moderate",
                    "rationale": "Blocking the event reduced downstream lipid accumulation.",
                    "references": [{"identifier": "PMID:111", "source": "pmid"}],
                },
            },
        ),
        (
            "v3",
            "KE:2",
            "Liver steatosis",
            {
                "measurement": "Histopathology",
                "essentiality": {
                    "evidence_call": "not_assessed",
                    "rationale": "Direct perturbation evidence has not yet been curated.",
                    "references": [],
                },
            },
        ),
    ]:
        response = _call_rpc(
            "tools/call",
            params={
                "name": "add_or_update_ke",
                "arguments": {
                    "draft_id": draft_id,
                    "version_id": version_id,
                    "author": "tester",
                    "summary": "add key event",
                    "identifier": identifier,
                    "title": title,
                    "event_role": "mie" if identifier == "KE:1" else "ao",
                    "attributes": attributes,
                },
            },
        )
        assert response.status_code == 200

    response = _call_rpc(
        "tools/call",
        params={
            "name": "add_or_update_ker",
            "arguments": {
                "draft_id": draft_id,
                "version_id": "v4",
                "author": "tester",
                "summary": "add ker",
                "identifier": "KER:1",
                "upstream": "KE:1",
                "downstream": "KE:2",
                "plausibility": "Strong mechanistic rationale",
                "attributes": {"empirical_support": "Dose concordance observed."},
            },
        },
    )
    assert response.status_code == 200

    response = _call_rpc(
        "tools/call",
        params={
            "name": "validate_draft_oecd",
            "arguments": {"draft_id": draft_id, "version_id": "v4"},
        },
    )
    assert response.status_code == 200
    structured = response.json()["result"]["structuredContent"]
    checks = {item["id"]: item["status"] for item in structured["results"]}
    assert checks["ke_essentiality_shape"] == "pass"
    assert checks["ke_essentiality_coverage"] == "pass"


def test_tools_call_add_or_update_ke_rejects_invalid_essentiality_payload() -> None:
    draft_id = "mcp-essentiality-fail"
    response = _call_rpc(
        "tools/call",
        params={
            "name": "create_draft_aop",
            "arguments": {
                "draft_id": draft_id,
                "title": "PXR activation leading to liver steatosis",
                "description": "MCP smoke draft.",
                "adverse_outcome": "Liver steatosis",
                "applicability": {"species": "human", "life_stage": "adult", "sex": "female"},
                "references": [{"title": "Example reference"}],
                "author": "tester",
                "summary": "create draft",
            },
        },
    )
    assert response.status_code == 200

    response = _call_rpc(
        "tools/call",
        params={
            "name": "add_or_update_ke",
            "arguments": {
                "draft_id": draft_id,
                "version_id": "v2",
                "author": "tester",
                "summary": "bad ke",
                "identifier": "KE:1",
                "title": "PXR activation",
                "attributes": {
                    "essentiality": {
                        "evidence_call": "strong",
                        "rationale": "Invalid controlled vocabulary.",
                    }
                },
            },
        },
        request_id=2,
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == -32602
    assert "essentiality" in data["error"]["message"]
