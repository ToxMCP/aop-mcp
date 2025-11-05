from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.adapters import (
    CacheProtocol,
    SparqlClient,
    SparqlEndpoint,
    SparqlQueryError,
    SparqlUpstreamError,
    TemplateCatalog,
)


class MemoryCache(CacheProtocol):
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.data.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:  # noqa: ARG002 - ttl reserved for future use
        self.data[key] = value


@pytest.mark.asyncio
async def test_query_successful_response() -> None:
    expected_payload = {"head": {"vars": ["s"]}, "results": {"bindings": []}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["Content-Type"] == "application/sparql-query"
        assert request.headers["Accept"] == "application/sparql-results+json"
        assert request.url == httpx.URL("https://primary.example/sparql")
        assert request.content.decode("utf-8") == "SELECT * WHERE {?s ?p ?o}"
        return httpx.Response(200, json=expected_payload)

    transport = httpx.MockTransport(handler)

    async with SparqlClient(["https://primary.example/sparql"], transport=transport) as client:
        payload = await client.query("SELECT * WHERE {?s ?p ?o}")

    assert payload == expected_payload


@pytest.mark.asyncio
async def test_query_failover_to_secondary_endpoint() -> None:
    call_tracker: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        call_tracker.append(request.url.host)
        if request.url.host == "primary.example":
            return httpx.Response(503)
        return httpx.Response(200, json={"results": {"bindings": [{"s": {"value": "x"}}]}})

    transport = httpx.MockTransport(handler)

    endpoints = [
        SparqlEndpoint(url="https://primary.example/sparql", name="primary"),
        SparqlEndpoint(url="https://secondary.example/sparql", name="secondary"),
    ]

    async with SparqlClient(endpoints, transport=transport, max_retries=0) as client:
        payload = await client.query("SELECT * WHERE {?s ?p ?o}")

    assert payload["results"]["bindings"][0]["s"]["value"] == "x"
    assert call_tracker == ["primary.example", "secondary.example"]


@pytest.mark.asyncio
async def test_query_raises_on_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Bad Request")

    transport = httpx.MockTransport(handler)

    async with SparqlClient(["https://primary.example/sparql"], transport=transport) as client:
        with pytest.raises(SparqlQueryError):
            await client.query("SELECT * WHERE {?s ?p ?o}")


@pytest.mark.asyncio
async def test_query_raises_when_all_endpoints_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed", request=request)

    transport = httpx.MockTransport(handler)

    async with SparqlClient(["https://primary.example/sparql"], transport=transport, max_retries=0) as client:
        with pytest.raises(SparqlUpstreamError):
            await client.query("ASK {?s ?p ?o}")


@pytest.mark.asyncio
async def test_query_uses_cache_when_available() -> None:
    cache = MemoryCache()
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"results": {"bindings": []}})

    transport = httpx.MockTransport(handler)

    async with SparqlClient(["https://primary.example/sparql"], transport=transport, cache=cache) as client:
        await client.query("SELECT * WHERE {?s ?p ?o}")
        await client.query("SELECT * WHERE {?s ?p ?o}")

    assert call_count == 1


@pytest.mark.asyncio
async def test_query_template_renders_parameters() -> None:
    catalog = TemplateCatalog({
        "list_key_events": "SELECT * WHERE {{ ?s ?p ?o }} LIMIT {limit}",
    })

    captured_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_queries.append(request.content.decode("utf-8"))
        return httpx.Response(200, json={"results": {"bindings": []}})

    transport = httpx.MockTransport(handler)

    async with SparqlClient(["https://primary.example/sparql"], template_catalog=catalog, transport=transport) as client:
        await client.query_template("list_key_events", {"limit": 5})

    assert captured_queries == ["SELECT * WHERE { ?s ?p ?o } LIMIT 5"]
