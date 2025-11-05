from __future__ import annotations

import pytest

from src.adapters import AOPWikiAdapter, AOPDBAdapter, SparqlClient
from src.tools import SchemaValidationError, validate_payload

import httpx


def make_client(response_json: dict) -> SparqlClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    transport = httpx.MockTransport(handler)
    return SparqlClient(["https://sparql.example"], transport=transport)


@pytest.mark.asyncio
async def test_search_aops_schema_validation() -> None:
    payload = {
        "results": {
            "bindings": [
                {
                    "aop": {"value": "http://aopwiki.org/aops/1"},
                    "title": {"value": "Example"},
                    "shortName": {"value": "AOP1"},
                }
            ]
        }
    }

    async with make_client(payload) as client:
        adapter = AOPWikiAdapter(client, cache_ttl_seconds=0)
        results = await adapter.search_aops()

    validate_payload({"results": results}, namespace="read", name="search_aops.response.schema")


@pytest.mark.asyncio
async def test_map_chemical_to_aops_schema_validation() -> None:
    response_json = {
        "results": {
            "bindings": [
                {
                    "aop": {"value": "http://aopwiki.org/aops/25"},
                    "title": {"value": "Example"},
                    "stressId": {"value": "DSS:123"},
                }
            ]
        }
    }

    async with make_client(response_json) as client:
        adapter = AOPDBAdapter(client, cache_ttl_seconds=0)
        results = await adapter.map_chemical_to_aops(name="example")

    validate_payload({"results": results}, namespace="read", name="map_chemical_to_aops.response.schema")
