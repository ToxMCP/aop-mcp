"""Asynchronous SPARQL client with endpoint failover and template support."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import httpx

from src.instrumentation.cache import Cache
from src.instrumentation.metrics import MetricsRecorder

class SparqlClientError(Exception):
    """Base exception for SPARQL client errors."""


class SparqlQueryError(SparqlClientError):
    """Raised when the SPARQL endpoint rejects the request (4xx)."""


class SparqlUpstreamError(SparqlClientError):
    """Raised when all SPARQL endpoints fail or return 5xx errors."""


class CacheProtocol:
    """Simple protocol for cache hooks."""

    async def get(self, key: str) -> Any:  # pragma: no cover - protocol shim
        raise NotImplementedError

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:  # pragma: no cover - protocol shim
        raise NotImplementedError


@dataclass(frozen=True)
class SparqlEndpoint:
    """Represents a SPARQL endpoint with optional name."""

    url: str
    name: str | None = None


class TemplateCatalog:
    """Utility for registering and rendering SPARQL templates."""

    def __init__(self, templates: Mapping[str, str] | None = None) -> None:
        self._templates: MutableMapping[str, str] = dict(templates or {})

    def add(self, name: str, template: str) -> None:
        self._templates[name] = template

    def get(self, name: str) -> str:
        try:
            return self._templates[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"Template '{name}' is not registered") from exc

    def render(self, name: str, parameters: Mapping[str, Any] | None = None) -> str:
        template = self.get(name)
        params = parameters or {}
        try:
            return template.format(**params)
        except KeyError as exc:
            missing = exc.args[0]
            raise ValueError(f"Missing template parameter: {missing}") from exc

    @classmethod
    def from_directory(cls, directory: Path, suffix: str = ".sparql") -> "TemplateCatalog":
        templates: dict[str, str] = {}
        for path in directory.glob(f"*{suffix}"):
            templates[path.stem] = path.read_text(encoding="utf-8")
        return cls(templates=templates)


class SparqlClient:
    """HTTPX-powered async client with failover, retries, and caching hooks."""

    def __init__(
        self,
        endpoints: list[SparqlEndpoint] | list[str],
        *,
        template_catalog: TemplateCatalog | None = None,
        cache: CacheProtocol | Cache | None = None,
        metrics: MetricsRecorder | None = None,
        max_retries: int = 2,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not endpoints:
            raise ValueError("At least one SPARQL endpoint must be configured")

        self._endpoints: list[SparqlEndpoint] = [
            endpoint if isinstance(endpoint, SparqlEndpoint) else SparqlEndpoint(url=endpoint)
            for endpoint in endpoints
        ]

        self._catalog = template_catalog or TemplateCatalog()
        self._cache = cache
        self._metrics = metrics
        self._max_retries = max(0, max_retries)
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SparqlClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def query(
        self,
        query: str,
        *,
        cache_key: str | None = None,
        cache_ttl_seconds: int | None = None,
        use_cache: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        key = cache_key or self._hash_query(query)
        if use_cache and self._cache is not None:
            cached = await self._cache.get(key)
            if cached is not None:
                if self._metrics:
                    self._metrics.increment("sparql.cache_hit")
                return cached

        if self._metrics:
            with self._metrics.time("sparql.query_time"):
                response = await self._dispatch(query, timeout=timeout)
        else:
            response = await self._dispatch(query, timeout=timeout)

        if use_cache and self._cache is not None:
            await self._cache.set(key, response, ttl_seconds=cache_ttl_seconds)
        if self._metrics:
            self._metrics.increment("sparql.cache_miss")

        return response

    async def query_template(
        self,
        name: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        cache_ttl_seconds: int | None = None,
        use_cache: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        rendered = self._catalog.render(name, parameters)
        cache_key = f"template::{name}::{self._hash_query(rendered)}"
        return await self.query(
            rendered,
            cache_key=cache_key,
            cache_ttl_seconds=cache_ttl_seconds,
            use_cache=use_cache,
            timeout=timeout,
        )

    async def _dispatch(self, query: str, *, timeout: float | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for endpoint in self._endpoints:
            attempts = self._max_retries + 1
            for attempt in range(attempts):
                try:
                    response = await self._client.post(
                        endpoint.url,
                        content=query.encode("utf-8"),
                        timeout=timeout or self._timeout,
                    )
                except httpx.RequestError as exc:
                    last_error = exc
                    continue

                if response.status_code >= 500:
                    last_error = SparqlUpstreamError(
                        f"Endpoint '{endpoint.url}' returned {response.status_code}"
                    )
                    continue

                if response.status_code >= 400:
                    raise SparqlQueryError(
                        f"SPARQL query failed with status {response.status_code}: {response.text}"
                    )

                try:
                    return response.json()
                except ValueError as exc:
                    raise SparqlUpstreamError("Endpoint returned non-JSON response") from exc

            # reached retry limit for this endpoint -> try next

        raise SparqlUpstreamError("All SPARQL endpoints failed") from last_error

    @staticmethod
    def _hash_query(query: str) -> str:
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        return digest
