"""Scientific overlap, context honesty, and actual multi-round HTTP boundaries."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from jsonschema import validate
from pydantic import ValidationError

from src.server.api.server import create_app
from src.server.config.settings import get_settings
from src.server.tools import comparison
from src.server.tools.registry import tool_registry

PROTOCOL = "2026-07-28"
QUESTION = "aop-comparison-context-v1"


class Wiki:
    """Deliberately synthetic records; never used as live evidence."""
    calls = 0

    async def get_aop_assessment(self, identifier):
        self.calls += 1
        return {"id": identifier, "title": f"Synthetic {identifier}" if identifier != "AOP:999" else None,
                "molecular_initiating_events": [{"id": "KE:1", "title": "Initiation"}],
                "adverse_outcomes": [{"id": "KE:3", "title": "Outcome"}]}

    async def list_key_events(self, identifier):
        values = {"AOP:1": [1, 2], "AOP:2": [2, 3], "AOP:3": [4]}[identifier] if identifier != "AOP:999" else []
        return [{"id": f"KE:{value}", "title": "Identical label"} for value in values]

    async def list_kers(self, identifier):
        return [{"id": "KER:1"}] if identifier in {"AOP:1", "AOP:2"} else []

    async def get_key_event(self, identifier):
        return {"id": identifier, "title": "Identical label", "taxonomic_applicability": ["NCBITaxon:9606"],
                "measurement_methods": [], "sex_applicability": "female", "life_stage_applicability": None}

    async def get_ker(self, identifier):
        return {"id": identifier, "biological_plausibility": "Reported text", "empirical_support": "  ",
                "quantitative_understanding": None}


@pytest.fixture
def wiki(monkeypatch):
    value = Wiki()
    monkeypatch.setattr(comparison, "get_aop_wiki_adapter", lambda: value)
    return value


@pytest.mark.asyncio
async def test_shared_ids_unique_events_gaps_and_context(wiki):
    result = await comparison.compare_aops(comparison.CompareAopsInput(
        aop_ids=["AOP:1", "AOP:2"], species="human", life_stage="adult", sex="female"))
    validate(result, tool_registry.get_tool("compare_aops").output_schema)
    assert result["status"] == "completed"
    assert [item["id"] for item in result["pairs"][0]["shared_key_events"]] == ["KE:2"]
    assert result["pairs"][0]["unique_key_event_ids"] == {"AOP:1": ["KE:1"], "AOP:2": ["KE:3"]}
    assert result["pairs"][0]["shared_ker_ids"] == ["KER:1"]
    assert result["pairs"][0]["shared_adverse_outcomes"][0]["id"] == "KE:3"
    assert result["aops"][0]["key_events"][0]["url"] == "https://identifiers.org/aop.events/1"
    evidence = result["aops"][0]["context_evidence"]
    assert evidence["species_exact_match_count"] == 2
    assert evidence["sex_exact_match_count"] == 2
    assert evidence["life_stage_exact_match_count"] == 0
    assert evidence["assessment"] == "requires_expert_review"
    assert evidence["reported_taxa"] == ["NCBITaxon:9606"]
    assert evidence["reported_life_stages"] == []
    assert evidence["reported_sexes"] == ["female"]
    assert result["aops"][0]["evidence_gaps"][-1]["not_reported_fields"] == ["empirical_support", "quantitative_understanding"]
    assert any("literature" in item for item in result["limitations"])


@pytest.mark.asyncio
async def test_unspecified_does_not_default_to_human_or_adult(wiki):
    result = await comparison.compare_aops(comparison.CompareAopsInput(
        aop_ids=["AOP:1", "AOP:2", "AOP:3"], species="unspecified", life_stage="unspecified"))
    assert len(result["pairs"]) == 3
    assert result["requested_context"]["species"] == "unspecified"
    assert result["aops"][0]["context_evidence"]["species_exact_match_count"] == 0
    assert result["pairs"][1]["shared_key_events"] == []  # Equal labels never imply equal identities.


@pytest.mark.asyncio
async def test_missing_context_returns_actionable_fallback_without_fetch(wiki):
    result = await comparison.compare_aops(comparison.CompareAopsInput(aop_ids=["AOP:1", "AOP:2"]))
    assert result["missing_inputs"] == ["species", "life_stage"]
    assert result["aops"] == [] and wiki.calls == 0


@pytest.mark.parametrize("arguments", [
    {"aop_ids": ["AOP:1"]}, {"aop_ids": ["AOP:1"] * 2},
    {"aop_ids": ["AOP:1", "AOP:2", "AOP:3", "AOP:4", "AOP:5"]},
    {"aop_ids": ["AOP:1", "AOP:2; DROP"]},
    {"aop_ids": ["AOP:1", "AOP:2"], "species": "nonsense"},
    {"aop_ids": ["AOP:1", "AOP:2"], "life_stage": " "},
    {"aop_ids": ["AOP:1", "AOP:2"], "life_stage": "adult", "unrequested": True},
])
def test_bad_inputs_are_rejected(arguments):
    with pytest.raises(ValidationError):
        comparison.CompareAopsInput.model_validate(arguments)


def post(client, arguments, *, modern=True, capabilities=True, bearer="guided-test-token", **extra):
    params = {"name": "compare_aops", "arguments": arguments, **extra}
    headers = {"Authorization": "Bearer " + bearer}
    if modern:
        params["_meta"] = {"io.modelcontextprotocol/protocolVersion": PROTOCOL,
                           "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}} if capabilities else {}}
        headers.update({"MCP-Protocol-Version": PROTOCOL, "Mcp-Method": "tools/call", "Mcp-Name": "compare_aops",
                        "Accept": "application/json, text/event-stream"})
    response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": params})
    return response.json()


@pytest.fixture
def client(monkeypatch, wiki):
    monkeypatch.setenv("AOP_MCP_ENVIRONMENT", "test")
    monkeypatch.setenv("AOP_MCP_AUTH_MODE", "bearer")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_TOKEN", "guided-test-token")
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_SCOPES", "toxmcp:read,toxmcp:live")
    monkeypatch.setenv("AOP_MCP_ALLOWED_ORIGINS", "")
    get_settings.cache_clear()
    try:
        with TestClient(create_app(), base_url="http://localhost:8000") as value:
            yield value
    finally:
        get_settings.cache_clear()


def test_modern_question_resume_and_sources(client):
    arguments = {"aop_ids": ["AOP:1", "AOP:2"]}
    pending = post(client, arguments)["result"]
    assert pending["resultType"] == "input_required"
    assert not pending["requestState"].startswith("{")
    assert pending["inputRequests"][QUESTION]["params"]["requestedSchema"]["required"] == ["species", "life_stage"]
    done = post(client, arguments, requestState=pending["requestState"], inputResponses={
        QUESTION: {"action": "accept", "content": {"species": "human", "life_stage": "adult"}}})["result"]
    assert done["structuredContent"]["status"] == "completed"
    assert done["_meta"]["sources"][0]["name"] == "AOP-Wiki"
    assert "Sources:" in done["content"][0]["text"]


@pytest.mark.parametrize("action", ["decline", "cancel"])
def test_decline_and_cancel_fetch_nothing(client, wiki, action):
    from src.instrumentation.audit import tool_call_audit_log
    before = len(tool_call_audit_log.list_records())
    arguments = {"aop_ids": ["AOP:1", "AOP:2"]}
    pending = post(client, arguments)["result"]
    done = post(client, arguments, requestState=pending["requestState"], inputResponses={QUESTION: {"action": action}})["result"]
    assert done["structuredContent"]["status"] == "cancelled" and wiki.calls == 0
    records = tool_call_audit_log.list_records()[before:]
    assert len(records) == 2
    assert all(item.tool_name == "compare_aops" and item.output_validation_status == "passed" for item in records)


@pytest.mark.parametrize("modern,capabilities", [(False, False), (True, False)])
def test_noninteractive_clients_can_retry_with_direct_arguments(client, modern, capabilities):
    arguments = {"aop_ids": ["AOP:1", "AOP:2"]}
    pending = post(client, arguments, modern=modern, capabilities=capabilities)["result"]
    assert pending["structuredContent"]["status"] == "input_required"
    done = post(client, {**arguments, "species": "human", "life_stage": "adult"}, modern=modern, capabilities=capabilities)
    assert done["result"]["structuredContent"]["status"] == "completed"


@pytest.mark.parametrize("variation", ["tamper", "arguments", "extra_answer", "missing_answer", "no_state"])
def test_resume_cannot_change_original_request_or_form(client, wiki, variation):
    arguments = {"aop_ids": ["AOP:1", "AOP:2"], "species": "human"}
    pending = post(client, arguments)["result"]
    state = pending["requestState"]
    content = {"life_stage": "adult"}
    if variation == "tamper": state = "broken-token"
    if variation == "arguments": arguments = {**arguments, "aop_ids": ["AOP:1", "AOP:3"]}
    if variation == "extra_answer": content["species"] = "mouse"
    if variation == "missing_answer": content = {}
    if variation == "no_state": state = None
    result = post(client, arguments, requestState=state, inputResponses={QUESTION: {"action": "accept", "content": content}})
    assert result["error"]["code"] == -32602 and wiki.calls == 0


def test_context_question_only_asks_for_missing_field(client):
    pending = post(client, {"aop_ids": ["AOP:1", "AOP:2"], "species": "mouse"})["result"]
    assert pending["inputRequests"][QUESTION]["params"]["requestedSchema"]["required"] == ["life_stage"]


def test_scopes_checked_before_question_or_data(client, monkeypatch, wiki):
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_SCOPES", "toxmcp:read")
    get_settings.cache_clear()
    with TestClient(create_app(), base_url="http://localhost:8000") as limited:
        denied = post(limited, {"aop_ids": ["AOP:1", "AOP:2"]})
        assert denied["error"]["code"] == -32003
        assert denied["error"]["data"]["missingScopes"] == ["toxmcp:live"] and wiki.calls == 0


def test_unknown_aop_is_actionable_tool_error_with_no_partial_comparison(client):
    result = post(client, {"aop_ids": ["AOP:1", "AOP:999"], "species": "human", "life_stage": "adult"})["result"]
    assert result["isError"] is True
    assert "check the ID" in result["content"][0]["text"]
    assert "structuredContent" not in result


def test_expired_state_rejected_before_fetch(client, wiki, monkeypatch):
    import mcp.server.request_state as state_module
    arguments = {"aop_ids": ["AOP:1", "AOP:2"]}
    pending = post(client, arguments)["result"]
    now = state_module.time.time()
    monkeypatch.setattr(state_module.time, "time", lambda: now + 601)
    result = post(client, arguments, requestState=pending["requestState"], inputResponses={
        QUESTION: {"action": "accept", "content": {"species": "human", "life_stage": "adult"}}})
    assert result["error"]["code"] == -32602 and wiki.calls == 0


@pytest.mark.parametrize("shared_key", [False, True])
def test_separate_workers_require_shared_key(client, monkeypatch, wiki, shared_key):
    if shared_key:
        monkeypatch.setenv("AOP_MCP_REQUEST_STATE_KEY", "synthetic-integration-test-key-32-bytes")
        get_settings.cache_clear()
    arguments = {"aop_ids": ["AOP:1", "AOP:2"]}
    with TestClient(create_app(), base_url="http://localhost:8000") as first:
        pending = post(first, arguments)["result"]
    with TestClient(create_app(), base_url="http://localhost:8000") as second:
        resumed = post(second, arguments, requestState=pending["requestState"], inputResponses={
            QUESTION: {"action": "accept", "content": {"species": "human", "life_stage": "adult"}}})
    if shared_key:
        assert resumed["result"]["structuredContent"]["status"] == "completed"
    else:
        assert resumed["error"]["code"] == -32602 and wiki.calls == 0


def test_changed_bearer_identity_rejects_resume(client, monkeypatch, wiki):
    monkeypatch.setenv("AOP_MCP_REQUEST_STATE_KEY", "synthetic-integration-test-key-32-bytes")
    get_settings.cache_clear()
    arguments = {"aop_ids": ["AOP:1", "AOP:2"]}
    with TestClient(create_app(), base_url="http://localhost:8000") as first:
        pending = post(first, arguments)["result"]
    monkeypatch.setenv("AOP_MCP_AUTH_BEARER_TOKEN", "second-guided-test-identity")
    get_settings.cache_clear()
    with TestClient(create_app(), base_url="http://localhost:8000") as second:
        result = post(second, arguments, bearer="second-guided-test-identity", requestState=pending["requestState"],
            inputResponses={QUESTION: {"action": "accept", "content": {"species": "human", "life_stage": "adult"}}})
    assert result["error"]["code"] == -32602 and wiki.calls == 0


@pytest.mark.asyncio
async def test_upstream_failure_returns_no_partial_comparison(wiki, monkeypatch):
    from src.adapters.sparql_client import SparqlClientError
    async def unavailable(identifier):
        raise SparqlClientError("Synthetic upstream failure")
    monkeypatch.setattr(wiki, "get_ker", unavailable)
    with pytest.raises(comparison.ComparisonError, match="No partial comparison"):
        await comparison.compare_aops(comparison.CompareAopsInput(
            aop_ids=["AOP:1", "AOP:2"], species="human", life_stage="adult"))
