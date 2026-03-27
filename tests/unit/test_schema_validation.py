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


@pytest.mark.asyncio
async def test_map_assay_to_aops_schema_validation() -> None:
    response_json = {
        "results": {
            "bindings": [
                {
                    "aop": {"value": "http://aopwiki.org/aops/25"},
                    "title": {"value": "Example"},
                }
            ]
        }
    }

    async with make_client(response_json) as client:
        adapter = AOPDBAdapter(client, cache_ttl_seconds=0, comptox_client=None)
        results = await adapter.map_assay_to_aops("HTS123")

    validate_payload({"results": results}, namespace="read", name="map_assay_to_aops.response.schema")


def test_list_assays_for_aop_schema_validation_with_diagnostics() -> None:
    payload = {
        "results": [],
        "diagnostics": {
            "aop_id": "AOP:529",
            "comptox_api_key_configured": False,
            "stressor_count": 0,
            "chemical_match_count": 0,
            "bioactivity_hit_count": 0,
            "returned_assay_count": 0,
            "empty_reason": "missing_comptox_api_key",
            "warnings": ["CompTox API key is not configured."],
        },
    }

    validate_payload(payload, namespace="read", name="list_assays_for_aop.response.schema")


def test_list_assays_for_aops_schema_validation_with_diagnostics() -> None:
    payload = {
        "results": [],
        "diagnostics": {
            "requested_aop_ids": ["AOP:529", "AOP:591"],
            "processed_aop_ids": ["AOP:529", "AOP:591"],
            "returned_assay_count": 0,
            "per_aop": [
                {
                    "aop_id": "AOP:529",
                    "comptox_api_key_configured": True,
                    "stressor_count": 1,
                    "chemical_match_count": 0,
                    "bioactivity_hit_count": 0,
                    "returned_assay_count": 0,
                    "empty_reason": "no_comptox_chemical_match",
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }

    validate_payload(payload, namespace="read", name="list_assays_for_aops.response.schema")


def test_list_assays_for_query_schema_validation_with_diagnostics() -> None:
    payload = {
        "query": "liver steatosis",
        "selected_aops": [{"id": "AOP:529", "title": "PPAR steatosis"}],
        "results": [],
        "diagnostics": {
            "query": "liver steatosis",
            "matched_aop_count": 3,
            "selected_aop_count": 1,
            "returned_assay_count": 0,
            "per_aop": [
                {
                    "aop_id": "AOP:529",
                    "comptox_api_key_configured": True,
                    "stressor_count": 1,
                    "chemical_match_count": 1,
                    "bioactivity_hit_count": 0,
                    "returned_assay_count": 0,
                    "empty_reason": "no_bioactivity_hits_after_filtering",
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }

    validate_payload(payload, namespace="read", name="list_assays_for_query.response.schema")


def test_list_assays_for_aop_schema_rejects_invalid_empty_reason() -> None:
    payload = {
        "results": [],
        "diagnostics": {
            "aop_id": "AOP:529",
            "comptox_api_key_configured": True,
            "stressor_count": 0,
            "chemical_match_count": 0,
            "bioactivity_hit_count": 0,
            "returned_assay_count": 0,
            "empty_reason": "wrong_value",
            "warnings": [],
        },
    }

    with pytest.raises(SchemaValidationError):
        validate_payload(payload, namespace="read", name="list_assays_for_aop.response.schema")
