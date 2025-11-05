"""Simple benchmark runner for SPARQL client and publish planners."""

from __future__ import annotations

import time

from src.adapters import SparqlClient, SparqlEndpoint
from src.instrumentation.cache import InMemoryCache
from src.instrumentation.metrics import MetricsRecorder


def benchmark_sparql(query: str) -> dict[str, float]:
    endpoints = [SparqlEndpoint(url="https://example.org/sparql")]
    metrics = MetricsRecorder()
    cache = InMemoryCache()
    client = SparqlClient(endpoints, cache=cache, metrics=metrics, max_retries=0)
    results = {"cold": 0.0, "warm": 0.0}
    start = time.perf_counter()
    try:
        client.query(query)
    except Exception:
        pass
    results["cold"] = time.perf_counter() - start
    start = time.perf_counter()
    try:
        client.query(query)
    except Exception:
        pass
    results["warm"] = time.perf_counter() - start
    return results

