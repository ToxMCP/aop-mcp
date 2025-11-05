# Taskmaster MCP for AOP

This repository bootstraps the Taskmaster MCP service that exposes read and
write tools over Adverse Outcome Pathway resources.

## Layout
- `src/`: Core adapters, semantic services, draft store, publish planners, and
  instrumentation utilities.
- `src/server`: MCP server implementation (FastAPI + JSON-RPC) mirroring the
  O-QT MCP structure.
- `docs/`: Architecture decision records, tool/resource contracts, compliance
  checklist, quickstart guides, and performance reports.
- `tests/`: Unit tests, golden fixtures, and MCP server smoke tests.

## Getting Started
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn src.server.api.server:app --host 0.0.0.0 --port 8000
```

Visit `http://127.0.0.1:8000/health` for a liveness check. The MCP endpoint is
available at `http://127.0.0.1:8000/mcp`; tools include read adapters
(`search_aops`, `get_aop`, `map_chemical_to_aops`), semantic utilities, and
write-path draft operations (`create_draft_aop`, `add_or_update_ke`, etc.).

## Current Status
- Phase A–F feature set implemented (adapters, semantics, draft store, publish
  planners, async jobs, compliance harness, benchmarks).
- MCP server compatible with Codex CLI, Gemini CLI, Claude Code, and other
  MCP-aware agents.
- Structured logging, metrics, and audit verification utilities in place for
  hardening and alerting pipelines.
