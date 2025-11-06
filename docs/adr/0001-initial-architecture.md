# 0001 - Initial Architecture Direction

## Status
Accepted (drafted 2025-11-05, pending review)

## Context
The AOP MCP server must expose read/write tooling over AOP knowledge bases. The
programme in `information.md` spans discovery tooling (search, map, evidence)
and authoring tooling (draft, validate, publish) with strong reuse of PBPK MCP
infrastructure. We need an architecture that:

- Keeps FastAPI at the core to maximise reuse of existing auth/audit/job
  frameworks.
- Organises integrations around adapters (AOP-Wiki, AOP-DB, CompTox,
  MediaWiki, AOPOntology) with strict schema boundaries.
- Adds semantic services for ontology harmonisation, provenance, and ID
  minting.
- Supports async execution for expensive SPARQL queries and export jobs.
- Provides clear surfaces for LangGraph agents to orchestrate read/write flows.

## Decision
Adopt a layered FastAPI application with explicit boundaries:

```
Clients / Agents ─▶ Tool Layer ─▶ Service Layer ─▶ Integration Adapters
                         │              │
                         │              └─► Semantic Services
                         │
                         └─► Job Service & Audit/Persistence Utilities
```

- **Tool layer**: MCP tool handlers validating JSON Schemas, enforcing RBAC,
  emitting audit events, and delegating to services.
- **Service layer**: Domain services for draft management, publish planning,
  semantic enrichment, and evidence assembly.
- **Integration adapters**: SPARQL/API clients with retry/failover controls,
  kept isolated behind abstractions.
- **Async job service**: Reuse PBPK job runner to offload long-running SPARQL
  queries, ingest, and export tasks while surfacing status endpoints.
- **Semantic services**: Modules handling CURIE validation, applicability
  mapping, evidence matrix generation, and ontology alignment.
- **Audit/provenance**: Hash-chained audit log reused from PBPK MCP with
  additional PROV-O blocks for write operations.

## System context

```
            +--------------------+
            |  LangGraph Agent   |
            +----------+---------+
                       |
                       | MCP (list_tools/call_tool)
                       v
+----------------------+-------------------+
|        AOP MCP FastAPI (Tool Layer)      |
|  - JSON schema validation                |
|  - RBAC enforcement                      |
|  - Audit events                          |
+---------------+--------------------------+
                |
                | service calls
                v
+---------------+--------------------------+
|   Domain Services & Semantic Utilities   |
|  - Draft store / publish planners        |
|  - Evidence & applicability services     |
|  - Job orchestration (async)             |
+---------------+--------------------------+
                |
                | adapter APIs
                v
+-----+-----+  +------+  +--------+  +----------+  +---------+
|AOP- Wiki|  |AOP-DB|  |CompTox |  |MediaWiki |  |AOPOntology|
| SPARQL  |  |SPARQL|  |  API   |  | Action API| |  OWL Store|
+---------+  +------+  +--------+  +----------+  +---------+
```

## Component responsibilities

- **Adapters** handle SPARQL/API invocation, result normalization, caching
  hooks, and error taxonomy mapping. Templates live alongside schema fixtures.
- **Draft store** persists write-path state with versioning, diff engine, and
  PROV-O provenance.
- **Publish planners** translate validated drafts into MediaWiki edit plans and
  OWL deltas, always supporting dry-run output.
- **Semantic services** enforce ontology policies, CURIE minting, applicability
  normalization, and evidence aggregation.
- **Async job service** exposes queue/status endpoints, enabling clients to
  monitor long-running operations without blocking.
- **Audit/logging** module emits hash-chained records, correlating user/session
  data with tool execution outcomes.

## Rationale

- Aligns with architecture drivers documented in
  `docs/adr/architecture-drivers.md`, keeping functional scope partitioned by
  phase while maximising reuse.
- Separating tool handlers from services ensures MCP contracts remain stable
  even if underlying storage or adapters evolve.
- Embedding semantic services inside the service layer keeps ontology-specific
  logic away from adapter code, simplifying testing and reuse.

## Consequences
- Enables incremental development across read and write tool phases; each layer
  can be delivered iteratively following task breakdown.
- Keeps compatibility with PBPK MCP deployment, auth, and job orchestration
  patterns, reducing bootstrap effort.
- Introduces additional modules (semantic services, draft store) that require
  dedicated testing and documentation up front.
- Requires early setup of validation schemas, ontology mapping utilities, and
  audit extensions to avoid downstream rework.
