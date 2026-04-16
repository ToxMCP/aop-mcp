from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx
import pytest

from src.adapters import (
    CacheProtocol,
    CircuitBreakerConfig,
    SparqlClient,
    SparqlEndpoint,
    SparqlQueryError,
    SparqlUpstreamError,
    TemplateCatalog,
)
from src.instrumentation.cache import InMemoryCache


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
async def test_query_supports_sync_cache_implementation() -> None:
    cache = InMemoryCache()
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"results": {"bindings": []}})

    transport = httpx.MockTransport(handler)

    async with SparqlClient(
        ["https://primary.example/sparql"],
        transport=transport,
        cache=cache,
    ) as client:
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


def test_render_safe_escapes_literals() -> None:
    catalog = TemplateCatalog({"test": 'FILTER(CONTAINS(?label, "{name}"))'})
    rendered = catalog.render_safe("test", literals={"name": 'foo"bar'})
    assert rendered == 'FILTER(CONTAINS(?label, "foo\\"bar"))'


def test_render_safe_validates_uris() -> None:
    catalog = TemplateCatalog({"test": "BIND(<{iri}> AS ?s)"})
    rendered = catalog.render_safe("test", uris={"iri": "https://example.org/aop/1"})
    assert rendered == "BIND(<https://example.org/aop/1> AS ?s)"


def test_render_safe_rejects_invalid_uris() -> None:
    catalog = TemplateCatalog({"test": "BIND(<{iri}> AS ?s)"})
    with pytest.raises(ValueError, match="Invalid URI scheme"):
        catalog.render_safe("test", uris={"iri": "javascript:alert(1)"})


def test_render_safe_validates_ints() -> None:
    catalog = TemplateCatalog({"test": "LIMIT {limit}"})
    rendered = catalog.render_safe("test", ints={"limit": 25})
    assert rendered == "LIMIT 25"


def test_render_safe_accepts_fragments() -> None:
    catalog = TemplateCatalog({"test": "{clause} LIMIT {limit}"})
    rendered = catalog.render_safe(
        "test",
        fragments={"clause": "SELECT * WHERE {?s ?p ?o}"},
        ints={"limit": 10},
    )
    assert rendered == "SELECT * WHERE {?s ?p ?o} LIMIT 10"


def test_render_safe_allows_empty_uri() -> None:
    catalog = TemplateCatalog({"test": "FILTER(STRLEN(\"{cas}\") > 0) <{uri}>"})
    rendered = catalog.render_safe(
        "test",
        literals={"cas": ""},
        uris={"uri": ""},
    )
    assert rendered == 'FILTER(STRLEN("") > 0) <>'


def test_render_safe_raises_on_missing_parameter() -> None:
    catalog = TemplateCatalog({"test": "LIMIT {limit}"})
    with pytest.raises(ValueError, match="Missing template parameter"):
        catalog.render_safe("test", ints={})


@pytest.mark.asyncio
async def test_query_template_with_safe_render() -> None:
    catalog = TemplateCatalog({
        "get_aop": "SELECT * WHERE {{ <{aop_iri}> ?p ?o }} LIMIT {limit}",
    })

    captured_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_queries.append(request.content.decode("utf-8"))
        return httpx.Response(200, json={"results": {"bindings": []}})

    transport = httpx.MockTransport(handler)

    async with SparqlClient(["https://primary.example/sparql"], template_catalog=catalog, transport=transport) as client:
        # Adapters call catalog.render_safe directly; query_template remains backward-compatible.
        query = catalog.render_safe(
            "get_aop",
            uris={"aop_iri": "https://example.org/aop/1"},
            ints={"limit": 5},
        )
        await client.query(query)

    assert captured_queries == ["SELECT * WHERE { <https://example.org/aop/1> ?p ?o } LIMIT 5"]


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=60.0)

    async with SparqlClient(
        ["https://primary.example/sparql"],
        transport=transport,
        max_retries=0,
        retry_base_delay=0.0,
        circuit_breaker_config=config,
    ) as client:
        # First two failures should hit the endpoint.
        with pytest.raises(SparqlUpstreamError):
            await client.query("SELECT * WHERE {?s ?p ?o}")
        with pytest.raises(SparqlUpstreamError):
            await client.query("SELECT * WHERE {?s ?p ?o}")
        # Third call should be rejected by the open circuit breaker.
        with pytest.raises(SparqlUpstreamError) as exc_info:
            await client.query("SELECT * WHERE {?s ?p ?o}")

    assert call_count == 2
    assert exc_info.value.__cause__ is not None
    assert "Circuit breaker open" in str(exc_info.value.__cause__)


@pytest.mark.asyncio
async def test_exponential_backoff_on_retry(monkeypatch) -> None:
    call_count = 0
    sleep_delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(random, "uniform", lambda _a, _b: 0.5)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)

    async with SparqlClient(
        ["https://primary.example/sparql"],
        transport=transport,
        max_retries=2,
        retry_base_delay=0.1,
        retry_max_delay=1.0,
        enable_circuit_breaker=False,
    ) as client:
        with pytest.raises(SparqlUpstreamError):
            await client.query("SELECT * WHERE {?s ?p ?o}")

    # 3 attempts (initial + 2 retries) on a single endpoint
    assert call_count == 3
    # Two sleeps between the three attempts
    assert len(sleep_delays) == 2
    # With fixed jitter: 0.1*1 + 0.5 == 0.6, 0.1*2 + 0.5 == 0.7
    assert sleep_delays == [0.6, 0.7]


@pytest.mark.asyncio
async def test_failover_skips_open_circuit() -> None:
    primary_calls = 0
    secondary_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal primary_calls, secondary_calls
        if request.url.host == "primary.example":
            primary_calls += 1
            return httpx.Response(503)
        secondary_calls += 1
        return httpx.Response(200, json={"results": {"bindings": []}})

    transport = httpx.MockTransport(handler)
    config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60.0)

    endpoints = [
        SparqlEndpoint(url="https://primary.example/sparql"),
        SparqlEndpoint(url="https://secondary.example/sparql"),
    ]

    async with SparqlClient(
        endpoints,
        transport=transport,
        max_retries=0,
        retry_base_delay=0.0,
        circuit_breaker_config=config,
    ) as client:
        # First call opens primary circuit and fails over to secondary.
        payload = await client.query("SELECT * WHERE {?s ?p ?o}")
        assert payload == {"results": {"bindings": []}}
        # Second call should skip primary entirely because circuit is open.
        payload = await client.query("SELECT * WHERE {?s ?p ?o}")
        assert payload == {"results": {"bindings": []}}

    assert primary_calls == 1
    assert secondary_calls == 2
