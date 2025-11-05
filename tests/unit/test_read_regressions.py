from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.adapters import AOPWikiAdapter, AOPDBAdapter, SparqlClient, CompToxClient
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


def test_comp_tox_extracts_identifiers_from_fixture() -> None:
    fixture = load_fixture(BASE_DIR / "comp_tox" / "chemical_aspirin.json")
    from src.adapters import extract_identifiers

    identifiers = extract_identifiers(fixture)
    assert identifiers["casrn"] == "50-78-2"
