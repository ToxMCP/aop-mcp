# Taskmaster MCP Activation Notes

Derived from `information.md` to support Taskmaster planning.

- Mission: build an AOP-focused MCP with read/write tooling across AOP-Wiki, AOP-DB, CompTox, MediaWiki, and AOPOntology sources.
- Architectural backbone: FastAPI service with adapters, semantic services, draft store, async jobs, auth/audit reuse from PBPK MCP.
- Tool surface: read (`search_aops`, `get_aop`, `list_key_events`, `list_kers`, `find_paths`, `map_chemical_to_aops`, `map_assay_to_aops`, `get_applicability`, `get_evidence_matrix`, `graph_query`), write (`create_draft_aop`, `add_or_update_ke`, `add_or_update_ker`, `link_stressor`, `validate_draft`, `propose_publish`, `publish`, optional `export_effectopedia`).
- Error taxonomy: UpstreamUnavailable, AmbiguousMapping, EditorialConflict, SemanticViolation.
- Security/ops: RBAC roles (author, reviewer, publisher), hash-chained audit logs, SPARQL safety guardrails, dual endpoint failover, dry-run publish plans.
- Testing focus: adapter snapshots, schema validation, semantic checks, integration against SPARQL mirrors, MediaWiki conflict simulation, job service compliance.

Use this overview when spinning up Taskmaster tasks or reports.
