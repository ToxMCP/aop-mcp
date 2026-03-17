from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.adapters import AOPWikiAdapter, SparqlClient


def make_client(handler: httpx.MockTransport) -> SparqlClient:
    return SparqlClient(["https://sparql.example/aopwiki"], transport=handler)


@pytest.mark.asyncio
async def test_search_aops_filters_and_normalizes_results() -> None:
    captured_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_queries.append(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "aop": {"value": "http://aopwiki.org/aops/123"},
                            "title": {"value": "Estrogen leads to reproductive failure"},
                            "shortName": {"value": "AOP123"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        results = await adapter.search_aops(text="Estrogen", limit=5)

    assert len(results) == 1
    assert results[0]["id"] == "AOP:123"
    assert results[0]["title"] == "Estrogen leads to reproductive failure"
    assert "LIMIT 5" in captured_queries[0]
    assert 'OPTIONAL { ?aop dc:description ?abstract }' in captured_queries[0]
    assert 'FILTER (?score > 0 && ?matchCount >= 1)' in captured_queries[0]
    assert 'ORDER BY DESC(?surfaceMatchCount) DESC(?score) LCASE(?title)' in captured_queries[0]
    assert 'CONTAINS(LCASE(COALESCE(?title, "")), "estrogen")' in captured_queries[0]
    assert 'CONTAINS(LCASE(COALESCE(?abstract, "")), "estrogen")' in captured_queries[0]


@pytest.mark.asyncio
async def test_search_aops_expands_common_liver_synonyms() -> None:
    captured_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_queries.append(request.content.decode("utf-8"))
        return httpx.Response(200, json={"results": {"bindings": []}})

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        await adapter.search_aops(text="liver steatosis", limit=5)

    assert '"hepatic"' in captured_queries[0]
    assert '"fatty liver"' in captured_queries[0]


@pytest.mark.asyncio
async def test_get_aop_returns_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        assert "<https://identifiers.org/aop/42> dc:title ?title ." in query
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "title": {"value": "Oxidative stress"},
                            "shortName": {"value": "AOP42"},
                            "status": {"value": "OECD:Draft"},
                            "abstract": {"value": "Mechanistic description"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        record = await adapter.get_aop("AOP:42")

    assert record["id"] == "AOP:42"
    assert record["short_name"] == "AOP42"
    assert record["status"] == "OECD:Draft"
    assert record["abstract"] == "Mechanistic description"


@pytest.mark.asyncio
async def test_list_key_events_normalizes_ke_identifiers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "<https://identifiers.org/aop/99> aopo:has_key_event ?ke ." in request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "ke": {"value": "http://aopwiki.org/events/567"},
                            "label": {"value": "Mitochondrial dysfunction"},
                            "eventType": {"value": "Cellular"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        key_events = await adapter.list_key_events("AOP:99")

    assert key_events == [
        {
            "id": "KE:567",
            "iri": "http://aopwiki.org/events/567",
            "title": "Mitochondrial dysfunction",
            "event_type": "Cellular",
        }
    ]


@pytest.mark.asyncio
async def test_list_kers_returns_upstream_and_downstream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "ker": {"value": "http://aopwiki.org/relationships/888"},
                            "upstream": {"value": "http://aopwiki.org/events/100"},
                            "downstream": {"value": "http://aopwiki.org/events/200"},
                            "plausibility": {"value": "strong"},
                            "status": {"value": "KC-curated"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        relationships = await adapter.list_kers("AOP:500")

    assert relationships == [
        {
            "id": "KER:888",
            "iri": "http://aopwiki.org/relationships/888",
            "upstream": {"id": "KE:100", "iri": "http://aopwiki.org/events/100"},
            "downstream": {"id": "KE:200", "iri": "http://aopwiki.org/events/200"},
            "plausibility": "strong",
            "status": "KC-curated",
        }
    ]
