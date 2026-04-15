"""Asynchronous SPARQL client with endpoint failover and template support."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import httpx

from src.instrumentation.cache import Cache
from src.instrumentation.metrics import MetricsRecorder


import logging

async def _resolve_maybe_awaitable(value: Any) -> Any:
    """Return awaited value when the input is awaitable, otherwise pass through."""

    if inspect.isawaitable(value):
        return await value
    return value

logger = logging.getLogger(__name__)

class SparqlClientError(Exception):
    """Base exception for SPARQL client errors."""


class SparqlQueryError(SparqlClientError):
    """Raised when the SPARQL endpoint rejects the request (4xx)."""


class SparqlUpstreamError(SparqlClientError):
    """Raised when all SPARQL endpoints fail or return 5xx errors."""


class CircuitBreakerOpen(SparqlUpstreamError):
    """Raised when the circuit breaker for an endpoint is open."""


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


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for per-endpoint circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    success_threshold: int = 2


class CircuitBreaker:
    """Simple in-memory circuit breaker for SPARQL endpoint protection."""

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(self, func, *args, **kwargs):
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                else:
                    raise CircuitBreakerOpen("SPARQL endpoint circuit breaker is OPEN")

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpen("Circuit breaker half-open limit reached")
                self.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        return (time.monotonic() - self.last_failure_time) >= self.config.recovery_timeout

    async def _on_success(self) -> None:
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
            else:
                self.failure_count = max(0, self.failure_count - 1)

    async def _on_failure(self) -> None:
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN


class TemplateCatalog:
    """Utility for registering and rendering SPARQL templates with safe binding."""

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
        """Legacy unsafe render. Prefer render_safe() for all production queries."""
        template = self.get(name)
        params = parameters or {}
        try:
            return template.format(**params)
        except KeyError as exc:
            missing = exc.args[0]
            raise ValueError(f"Missing template parameter: {missing}") from exc

    def render_safe(
        self,
        name: str,
        *,
        literals: Mapping[str, Any] | None = None,
        uris: Mapping[str, str] | None = None,
        ints: Mapping[str, int] | None = None,
        fragments: Mapping[str, str] | None = None,
    ) -> str:
        """Render template with safe, categorized parameter binding.

        - literals: escaped as SPARQL string literals.
        - uris: validated as URIs and passed through.
        - ints: validated as integers and passed through.
        - fragments: passed through verbatim (trusted structural fragments only).
        """
        template = self.get(name)
        replacements: dict[str, str] = {}

        for key, value in (literals or {}).items():
            replacements[key] = self._escape_sparql_literal(str(value))

        for key, value in (uris or {}).items():
            replacements[key] = self._validate_uri(value)

        for key, value in (ints or {}).items():
            replacements[key] = str(int(value))

        for key, value in (fragments or {}).items():
            replacements[key] = value

        try:
            return template.format(**replacements)
        except KeyError as exc:
            missing = exc.args[0]
            raise ValueError(f"Missing template parameter: {missing}") from exc

    @staticmethod
    def _escape_sparql_literal(value: str) -> str:
        """Escape a string for safe use inside a SPARQL double-quoted string literal."""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _validate_uri(value: str) -> str:
        """Validate that a value is a well-formed URI before injecting it.

        Empty string is allowed so templates can use FILTER guards to skip
        optional URI patterns safely.
        """
        if not isinstance(value, str):
            raise ValueError(f"URI must be a string, got {type(value)}")
        if value == "":
            return value
        allowed_schemes = ("http://", "https://", "urn:", "file:")
        if not any(value.startswith(s) for s in allowed_schemes):
            raise ValueError(f"Invalid URI scheme: {value!r}")
        return value

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
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 5.0,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        enable_circuit_breaker: bool = True,
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
        self._retry_base_delay = max(0.0, retry_base_delay)
        self._retry_max_delay = max(0.0, retry_max_delay)
        self._enable_circuit_breaker = enable_circuit_breaker
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            endpoint.url: CircuitBreaker(config=circuit_breaker_config)
            for endpoint in self._endpoints
        }
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
            cached = await _resolve_maybe_awaitable(self._cache.get(key))
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
            await _resolve_maybe_awaitable(
                self._cache.set(key, response, ttl_seconds=cache_ttl_seconds)
            )
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

    async def _execute_single(
        self,
        endpoint: SparqlEndpoint,
        query: str,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a single request against one endpoint and validate the response.

        Raises SparqlUpstreamError on 5xx or non-JSON responses.
        Raises SparqlQueryError on 4xx.
        """
        response = await self._client.post(
            endpoint.url,
            content=query.encode("utf-8"),
            timeout=timeout or self._timeout,
        )

        if response.status_code >= 500:
            raise SparqlUpstreamError(
                f"Endpoint '{endpoint.url}' returned {response.status_code}"
            )

        if response.status_code >= 400:
            raise SparqlQueryError(
                f"SPARQL query failed with status {response.status_code}: {response.text}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise SparqlUpstreamError("Endpoint returned non-JSON response") from exc

    async def _dispatch(self, query: str, *, timeout: float | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for endpoint in self._endpoints:
            circuit = self._circuit_breakers[endpoint.url]
            attempts = self._max_retries + 1
            for attempt in range(attempts):
                try:
                    if self._enable_circuit_breaker:
                        return await circuit.call(
                            self._execute_single,
                            endpoint,
                            query,
                            timeout=timeout,
                        )
                    return await self._execute_single(
                        endpoint,
                        query,
                        timeout=timeout,
                    )
                except CircuitBreakerOpen:
                    logger.warning("SPARQL circuit breaker open for %s", endpoint.url)
                    last_error = CircuitBreakerOpen(
                        f"Circuit breaker open for {endpoint.url}"
                    )
                    break  # skip retries, move to next endpoint
                except SparqlQueryError:
                    # 4xx client errors are not retryable; surface them immediately.
                    raise
                except Exception as exc:
                    logger.warning(
                        "SPARQL request to %s failed (attempt %d/%d): %s",
                        endpoint.url,
                        attempt + 1,
                        attempts,
                        exc,
                    )
                    last_error = exc
                    if attempt < attempts - 1 and self._retry_base_delay > 0:
                        delay = min(
                            self._retry_base_delay * (2 ** attempt) + random.uniform(0, 1),
                            self._retry_max_delay,
                        )
                        await asyncio.sleep(delay)
                    continue

            # reached retry limit for this endpoint -> try next

        raise SparqlUpstreamError("All SPARQL endpoints failed") from last_error

    @staticmethod
    def _hash_query(query: str) -> str:
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        return digest
