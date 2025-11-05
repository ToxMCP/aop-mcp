from __future__ import annotations

from src.instrumentation.cache import InMemoryCache
from src.instrumentation.metrics import MetricsRecorder


def test_in_memory_cache_respects_ttl() -> None:
    cache = InMemoryCache()
    cache.set("foo", "bar", ttl_seconds=0)
    assert cache.get("foo") is None


def test_metrics_recorder_tracks_counters_and_timings() -> None:
    metrics = MetricsRecorder()
    metrics.increment("sparql.cache_hit")
    with metrics.time("sparql.query_time"):
        pass

    assert metrics.counters["sparql.cache_hit"] == 1
    assert len(metrics.timings["sparql.query_time"]) == 1
