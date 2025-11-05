# Performance Benchmarks

## Objectives
- Measure baseline SPARQL query latency and cache effectiveness.
- Track job lifecycle timing (queue → completion) for async operations.
- Profile publish planners for large drafts to ensure dry-run plans remain fast.

## SPARQL benchmark
- Cold query latency (`sparql.cache_miss` timings) recorded via instrumentation.
- Warm cache latency (`sparql.cache_hit`) after query replay.
- Target: cached reads under 150ms for standard list/get operations.

## Job service timing
- Measure submit → running transition and running → completion durations.
- Emit metrics to ensure long-running tasks trigger async job offload rather than blocking.

## Publish planner profiling
- Use representative drafts (≥10 key events, ≥5 KERs) to time MediaWiki/OWL plan generation.
- Ensure dry-run planners execute under 200ms.

## Logging & alerting
- Structured logs now capture draft and job lifecycle events for use in alert pipelines.
- Alerts should trigger on repeated job failures, publish planner errors, or latency regressions.

## Future work
- Integrate automated benchmark runner that fails CI when regressions exceed thresholds.
- Add percentile-based reporting (p50/p95)
