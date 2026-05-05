# Testing & Validation Status — AOP MCP

_Last updated: 2026-05-05_

## Coverage snapshot

- **Unit + contract**: `make contract` wraps
  - `tests/unit/test_read_regressions.py`
  - `tests/unit/test_semantic_tools.py`
  - `tests/unit/test_write_tools.py`
  Each schema under `docs/contracts/schemas/` is asserted via `validate_payload` against recorded fixtures.
- **Cross-suite golden lane**: `python -m pytest tests/unit/test_registry_aop_draft_review_golden.py -q`
  - Rebuilds a deterministic draft with attached Registry `aop_context` support and verifies the frozen `Registry -> AOP draft review artifact` outputs under `tests/golden/cross_suite/`.
- **Trust/auditability lane**: `python -m pytest tests/unit/test_mcp_tool_audit.py tests/unit/test_trust_docs.py -q`
  - Covers process-local MCP audit records, durable JSONL hash-chain verification, bounded durable evidence export, runtime manifest schema coverage, and public trust-document guardrails.
- **MCP JSON-RPC smoke suite**: `make smoke`
  - Drives `/mcp` endpoint through `initialize`, `tools/list`, and a golden `tools/call` (`search_aops`).
  - Live call retained under `@pytest.mark.skip` for network-enabled environments.
- **Endpoint health**: `make check-endpoints` (or `make check-endpoints-offline` locally)
  - `scripts/check_endpoints.py` probes configured SPARQL endpoints with `ASK` queries and optionally captures sample responses.
- **Full test harness**: `make test` → contract + smoke + standard `pytest`.

## Execution matrix

| Tier | Command | Frequency | Notes |
| --- | --- | --- | --- |
| Unit/contract | `make contract` | PR / CI | Covers read+semantic+write schemas with golden fixtures |
| Cross-suite goldens | `python -m pytest tests/unit/test_registry_aop_draft_review_golden.py -q` | PR / CI | Verifies the deterministic Registry-attached draft review/export seam |
| Trust/auditability | `python -m pytest tests/unit/test_mcp_tool_audit.py tests/unit/test_trust_docs.py -q` | PR / CI | Verifies audit records, durable JSONL chain behavior, evidence export, and trust docs |
| Smoke (offline) | `make smoke` | PR / CI | Skips live network call; verifies JSON-RPC response envelope |
| Endpoint health | `make check-endpoints` | Nightly / on-demand | Requires outbound HTTPS to AOP-Wiki/AOP-DB; capture live samples |
| Endpoint health (offline) | `make check-endpoints-offline` | Local quick check | Skips network to verify script wiring |
| Full test suite | `make test` | PR / CI | Aggregates unit + smoke |

## Recent results

- Local `.venv/bin/python -m pytest -q`: all tests passed with the single live-network smoke test skipped (2026-05-05).
- The single skipped test remains `tests/unit/test_mcp_smoke.py::test_tools_call_search_aops_live`, which requires live SPARQL network access.
- GitHub Actions CI for the v0.9.0 trust/replay series succeeded across `Lint`, `Runtime Contract`, `test (3.11)`, and `test (3.12)` on 2026-05-05.
- Validated live-scientific example walkthrough captured in `docs/quickstarts/live-scientific-examples.md` using a running server on 2026-04-12.

## Outstanding items

1. **Live smoke validation** — enable the skipped JSON-RPC live call once the environment has network access; record payloads under `tests/golden/live/`.
2. **Connectivity automation** — schedule `make check-endpoints` via CI/nightly pipeline; alert when SPARQL mirrors fail.
3. **Failure-path fixtures** — extend contract suite with 4xx/5xx simulated responses for adapters and ensure error schemas are documented.
4. **Observation hooks** — integrate test command outputs into CI artifacts (coverage XML, logs) for centralized reporting.

## Usage reminders

- Pass `CHECK_ENDPOINTS_ARGS="--aop-id AOP:296 --search-limit 5"` to tweak sample capture without editing scripts.
- Update `docs/contracts/endpoint-matrix.md` with new mirrors or troubleshooting steps after incidents.
- When adding new MCP tools, extend schemas + fixtures + contract assertions before exposing them through the registry.
