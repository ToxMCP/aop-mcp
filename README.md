# AOP MCP Server

**Model Context Protocol endpoint for Adverse Outcome Pathway discovery, semantics, and draft authoring.**  
Use the same Taskmaster components we developed (read adapters, semantic services, write-path tooling, publish planners, async jobs) through any MCP-aware agent—Codex CLI, Claude Code, Gemini CLI, etc.

## Why this project exists

AOP knowledge work spans multiple heterogeneous sources (AOP-Wiki, AOP-DB, CompTox, MediaWiki, AOPOntology) and requires curated semantics plus draft/publish tooling. The AOP MCP server turns the full stack we built in this repository into an **open, programmable interface** so agents can:

- Query AOPs, key events, and KERs directly through MCP tools.
- Normalize applicability/evidence, manage drafts, and generate publish plans.
- Leverage async job orchestration, compliance harness, and structured logging for hardening.

The goal is to replicate the experience of the O-QT MCP server but for the AOP domain.

---

## Feature snapshot

| Capability | Description |
| --- | --- |
| 🧬 **AOP discovery adapters** | Read tooling for AOP-Wiki, AOP-DB, CompTox with schema-validated responses. |
| 🧭 **Semantic services** | CURIE normalization, applicability helper, evidence matrix utilities exposed as tools. |
| ✍️ **Draft authoring** | Write-path tools using the draft store (create/update KE/KER, link stressors) with provenance and diffing. |
| 📄 **Publish planners** | MediaWiki and AOPOntology OWL dry-run planners ready for reviewer/publisher workflows. |
| 🧾 **Compliance & audit** | Hash-chain verification, structured logging, metrics, benchmark targets. |
| 🤖 **Agent-friendly MCP** | JSON-RPC 2.0 server adhering to MCP spec, tested with Codex CLI, Claude Code, Gemini CLI. |

---

## Repository layout

```
AOP_MCP/
├── src/
│   ├── adapters/         # AOP-Wiki, AOP-DB, CompTox clients + schemas
│   ├── services/         # Draft store, publish planners, jobs, instrumentation
│   ├── tools/            # Semantic + write-path utilities (schema backed)
│   └── server/           # FastAPI MCP server (JSON-RPC, tool registry)
├── docs/
│   ├── adr/              # Architecture decision records
│   ├── contracts/        # JSON Schemas, endpoint matrix, compliance checklist
│   ├── quickstarts/      # How to use read/write/publish tools + MCP integration
│   └── reports/          # Performance benchmarks, hardening notes
├── tests/                # Unit tests, golden fixtures, MCP smoke tests
└── scripts/benchmarks.py # Placeholder benchmark runner
```

---

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn src.server.api.server:app --host 0.0.0.0 --port 8000
```

Visit `http://127.0.0.1:8000/health` for a liveness check. MCP tools are exposed at `http://127.0.0.1:8000/mcp`.

### MCP smoke test

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

You should see the AOP tool catalog (e.g., `search_aops`, `map_chemical_to_aops`, `create_draft_aop`).

---

## Configuration

Environment variables use the `AOP_MCP_` prefix. Key settings:

| Variable | Default | Description |
| --- | --- | --- |
| `AOP_MCP_ENVIRONMENT` | `development` | Included in `/health` and logs. |
| `AOP_MCP_LOG_LEVEL` | `INFO` | Log verbosity. |
| `AOP_MCP_AOP_WIKI_SPARQL_ENDPOINTS` | `https://sparql.aopwiki.org/sparql` | Comma-separated SPARQL endpoints. |
| `AOP_MCP_AOP_DB_SPARQL_ENDPOINTS` | `https://sparql.aopdb.org/sparql` | Comma-separated SPARQL endpoints. |
| `AOP_MCP_COMPTOX_BASE_URL` | `https://comptox.epa.gov/dashboard/api/` | CompTox API base URL. |
| `AOP_MCP_COMPTOX_API_KEY` | – | Optional CompTox API key. |

Extend the settings module (`src/server/config/settings.py`) if you need additional configuration (auth, job backend, etc.).

---

## Tool catalog (summary)

| Tool | Description |
| --- | --- |
| `search_aops` | Text search over AOP-Wiki. |
| `get_aop` | Retrieve metadata for a single AOP. |
| `list_key_events` / `list_kers` | Enumerate KEs/KERs for an AOP. |
| `map_chemical_to_aops` / `map_assay_to_aops` | Cross-map chemicals or assays via AOP-DB + CompTox. |
| `get_applicability` / `get_evidence_matrix` | Semantic normalization helpers. |
| `create_draft_aop` | Create a draft with applicability and references. |
| `add_or_update_ke` / `add_or_update_ker` | Modify draft graph components (with diffing + audit chain). |
| `link_stressor` | Attach stressors to the draft with provenance. |

Responses are validated against JSON Schemas under `docs/contracts/schemas/` to ensure MCP agents get consistent payloads.

---

## Integrating with coding agents

Any MCP-aware agent can connect by pointing to the base URL:

```json
{
  "endpoint": "http://127.0.0.1:8000/mcp"
}
```

Tested clients:
- **Codex CLI** – `codex mcp connect http://127.0.0.1:8000/mcp`
- **Gemini CLI** – add the server to `mcp_servers` in the CLI config.
- **Claude Code** – use the custom MCP server configuration.

Because the server exposes the standard `initialize`, `tools/list`, `tools/call`, and `shutdown` methods, everything behaves like the O-QT MCP server.

---

## Security & compliance

- Structured logging via `src/instrumentation/logging.py` (JSON payloads with draft/job context).
- Cache + metrics instrumentation for SPARQL queries (`sparql.cache_hit`, `sparql.cache_miss`).
- Audit chain verification helper (`src/instrumentation/audit.py`) plus docs/contracts/compliance/checklist.md.
- Async job service with status transitions and logging to support alerts on failures or long runtimes.

---

## Development notes

- Tests: `pytest`
- Benchmark stubs: `python scripts/benchmarks.py` (extend with real endpoints).
- Keep MCP tools in sync with the Taskmaster services—update JSON Schemas and docs (`docs/contracts/`, `docs/quickstarts/`) when payloads change.

---

## Roadmap

- Optional persistent job backend (Redis/Postgres) + LangGraph integration.
- Automated benchmark runner with thresholds feeding CI.
- Extended compliance automation (RBAC simulations, publish dry-run approvals).
- Additional MCP resources/prompts if AOP agents need pre-authored content.

---

## License

MIT (same as the Taskmaster MCP project).

