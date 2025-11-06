from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.adapters import AOPWikiAdapter, AOPDBAdapter, SparqlClient, CompToxClient, SparqlClientError
from src.tools import validate_payload

BASE_DIR = Path(__file__).resolve().parent.parent / "golden" / "read"


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_transport(payload: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_aop_wiki_search_regression() -> None:
    payload = load_fixture(BASE_DIR / "aop_wiki" / "search_aops.json")
    async with SparqlClient(["https://sparql.example"], transport=make_transport(payload)) as client:
        adapter = AOPWikiAdapter(client, cache_ttl_seconds=0)
        results = await adapter.search_aops()

    validate_payload({"results": results}, namespace="read", name="search_aops.response.schema")
    assert results[0]["id"] == "AOP:123"


@pytest.mark.asyncio
async def test_aop_wiki_get_aop_regression() -> None:
    payload = load_fixture(BASE_DIR / "aop_wiki" / "get_aop.json")
    async with SparqlClient(["https://sparql.example"], transport=make_transport(payload)) as client:
        adapter = AOPWikiAdapter(client, cache_ttl_seconds=0)
        record = await adapter.get_aop("AOP:123")

    validate_payload(record, namespace="read", name="get_aop.response.schema")
    assert record["status"] == "OECD:Approved"


@pytest.mark.asyncio
async def test_aop_db_map_chemical_regression() -> None:
    payload = load_fixture(BASE_DIR / "aop_db" / "map_chemical_to_aops.json")
    async with SparqlClient(["https://sparql.example"], transport=make_transport(payload)) as client:
        adapter = AOPDBAdapter(client, cache_ttl_seconds=0)
        records = await adapter.map_chemical_to_aops(inchikey="BSYNRYMUTXBXSQ-UHFFFAOYSA-N")

    validate_payload({"results": records}, namespace="read", name="map_chemical_to_aops.response.schema")
    assert records[0]["aop"]["id"] == "AOP:25"


@pytest.mark.asyncio
async def test_aop_db_map_assay_regression() -> None:
    payload = load_fixture(BASE_DIR / "aop_db" / "map_assay_to_aops.json")
    async with SparqlClient(["https://sparql.example"], transport=make_transport(payload)) as client:
        adapter = AOPDBAdapter(client, cache_ttl_seconds=0)
        records = await adapter.map_assay_to_aops("TOX21-72")

    validate_payload({"results": records}, namespace="read", name="map_assay_to_aops.response.schema")
    assert records[0]["aop"]["id"] == "AOP:30"
    assert records[0]["assay_id"] == "TOX21-72"


@pytest.mark.asyncio
async def test_aop_wiki_list_key_events_regression() -> None:
    payload = load_fixture(BASE_DIR / "aop_wiki" / "list_key_events.json")
    async with SparqlClient(["https://sparql.example"], transport=make_transport(payload)) as client:
        adapter = AOPWikiAdapter(client, cache_ttl_seconds=0)
        results = await adapter.list_key_events("AOP:123")

    validate_payload({"results": results}, namespace="read", name="list_key_events.response.schema")
    assert results[0]["id"] == "KE:100"


@pytest.mark.asyncio
async def test_aop_wiki_list_kers_regression() -> None:
    payload = load_fixture(BASE_DIR / "aop_wiki" / "list_kers.json")
    async with SparqlClient(["https://sparql.example"], transport=make_transport(payload)) as client:
        adapter = AOPWikiAdapter(client, cache_ttl_seconds=0)
        results = await adapter.list_kers("AOP:123")

    validate_payload({"results": results}, namespace="read", name="list_kers.response.schema")
    assert results[0]["id"] == "KER:888"


def test_comp_tox_extracts_identifiers_from_fixture() -> None:
    fixture = load_fixture(BASE_DIR / "comp_tox" / "chemical_aspirin.json")
    from src.adapters import extract_identifiers

    identifiers = extract_identifiers(fixture)
    assert identifiers["casrn"] == "50-78-2"


@pytest.mark.asyncio
async def test_aop_wiki_search_fallback_when_query_fails(monkeypatch) -> None:
    async def failing_query(self, query: str, **_: Any):  # type: ignore[no-untyped-def]
        raise SparqlClientError("network unavailable")

    monkeypatch.setattr(SparqlClient, "query", failing_query, raising=False)
    async with SparqlClient(["https://sparql.example"], transport=make_transport({})) as client:
        adapter = AOPWikiAdapter(client, cache_ttl_seconds=0)
        results = await adapter.search_aops(text="liver", limit=1)

    assert results and results[0]["id"] == "AOP:123"


@pytest.mark.asyncio
async def test_aop_db_map_chemical_fallback_when_query_fails(monkeypatch) -> None:
    async def failing_query(self, query: str, **_: Any):  # type: ignore[no-untyped-def]
        raise SparqlClientError("network unavailable")

    monkeypatch.setattr(SparqlClient, "query", failing_query, raising=False)
    async with SparqlClient(["https://sparql.example"], transport=make_transport({})) as client:
        adapter = AOPDBAdapter(client, cache_ttl_seconds=0)
        records = await adapter.map_chemical_to_aops(name="aspirin")

    assert records and records[0]["aop"]["id"] == "AOP:25"
