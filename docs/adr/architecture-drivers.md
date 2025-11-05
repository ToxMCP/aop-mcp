# Architecture Drivers — AOP MCP

## Mission context
- Deliver an MCP server focused on Adverse Outcome Pathways (AOPs), providing read, semantic, and write tooling aligned with the roadmap in `information.md`.
- Support both discovery workflows (search, browse, evidence review) and authoring workflows (drafting, editing, publishing AOP content) across AOP-Wiki, AOP-DB, CompTox, and AOPOntology sources.
- Reuse the PBPK MCP platform components (auth, audit trail, async job orchestration) where possible to accelerate delivery.

## Functional drivers
- **Read tooling**: Expose MCP tools for `search_aops`, `get_aop`, `list_key_events`, `list_kers`, `find_paths`, `map_chemical_to_aops`, `map_assay_to_aops`, `get_applicability`, `get_evidence_matrix`, and `graph_query` with consistent schema validation.
- **Write tooling**: Provide draft management (`create_draft_aop`, `add_or_update_ke`, `add_or_update_ker`, `link_stressor`, `validate_draft`) and publish planners capable of generating MediaWiki edits and AOPOntology OWL deltas with dry-run support.
- **Semantic services**: Offer ontology alignment, CURIE normalization/minting, applicability normalization, and evidence matrix generation consistent with AOPOntology and Biolink expectations.
- **Agent orchestration**: Enable LangGraph-based agent workflows that can chain read/write tools, surface explanations, and enforce confirmation for write operations.

## Data & integration drivers
- **Primary endpoints**: Consume AOP-Wiki SPARQL (VHP4Safety/OpenRiskNet mirrors), AOP-DB SPARQL, CompTox APIs, and MediaWiki Action API; emit OWL/RDF updates for AOPOntology stores.
- **Failover policies**: Maintain configurable primary/secondary SPARQL endpoints with retry/backoff guidance and health monitoring; document SLA assumptions per integration.
- **Schema alignment**: Normalize identifiers to Biolink Model categories and AOPOntology classes, recording provenance via W3C PROV-O blocks.
- **Caching & fixtures**: Support snapshot testing with golden SPARQL fixtures and enable response caching with invalidation hooks for high-cost queries.

## Quality attribute drivers
- **Reliability**: Provide dual endpoint failover and retry strategies for upstream outages, plus async job offloading for long-running queries.
- **Performance**: Track SPARQL query cost, cache high-demand responses, and benchmark agent/job flows as part of Phase E/F hardening.
- **Observability**: Emit structured logs with correlation IDs, metrics on adapter success/failure, and audit hash chaining for write operations.
  Lightweight metrics/time tracking added for SPARQL queries and job lifecycle events using instrumentation utilities.
- **Extensibility**: Keep adapters/semantic services modular so additional endpoints or ontology mappings can be plugged in without refactoring core flows.

## Security & compliance drivers
- **RBAC & approvals**: Enforce author/reviewer/publisher roles on write-path tools with staged review before MediaWiki/AOPOntology publication.
- **Auditability**: Capture tamper-evident logs and PROV-O provenance for all draft mutations and publish plans; reuse PBPK hash-chained audit design.
- **Threat coverage**: Extend threat model to address draft store integrity, MediaWiki CSRF choreography, OWL export handling, and cache poisoning risks.
- **Error taxonomy**: Standardize adapter and write-path errors into categories such as `UpstreamUnavailable`, `AmbiguousMapping`, `EditorialConflict`, and `SemanticViolation` to aid agent recovery.

## Reuse & constraints
- **Platform reuse**: Port PBPK MCP scaffolding (FastAPI project layout, async job runner, auth/audit middleware, testing harness) and adapt to AOP domain specifics.
- **Technology stack**: Stick with FastAPI + Python adapters, integrating existing JSON schema tooling and LangGraph-based agents.
- **Data contracts**: Maintain strict JSON Schema validation for all MCP tools, storing schemas under `docs/contracts` and ensuring CI enforcement.
- **Write safety**: Keep publish planners dry-run by default; live writes require explicit manual trigger with RBAC checks.

## Open questions & follow-ups
1. Confirm availability and rate limits for each SPARQL endpoint mirror; decide on default cache TTLs per integration.
2. Determine storage technology for draft store (graph DB vs document store) and how it aligns with provenance requirements.
3. Select queue/persistence backend for async job service (e.g., SQLite, Postgres, Redis) and whether PBPK solution can be lifted directly.
4. Clarify operational responsibilities for MediaWiki credentials and secret rotation cadence.
5. Evaluate need for additional export formats (Effectopedia) beyond initial MediaWiki/OWL scope.
