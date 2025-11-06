# Architecture Decision Records

This directory houses ADRs for the AOP MCP server. Number entries as
`NNNN-title.md` and capture context, decision, alternatives, and consequences
for each architectural choice.

## Index
- `architecture-drivers.md` — consolidated drivers, constraints, reusable
  components, and open questions grounding the Phase A decisions.
- `0001-initial-architecture.md` — accepted system context, layering, and reuse
  stance for the FastAPI-based MCP.
- `threat-model-write-path.md` — STRIDE analysis covering new draft/publish
  surfaces and mitigations.
- `draft-store-data-model.md` — data structures and services backing the write-path.
- `agent-workflow-notes.md` — LangGraph/async job considerations for Phase E.

## Follow-on implementation map
- **AOP-002**: Implement adapters and schemas per component boundaries captured
  in ADR 0001; seed fixtures referenced in the drivers doc.
- **AOP-003**: Stand up semantic services aligned with ontology alignment plan
  and CURIE rules.
- **AOP-004**: Build draft store/publish planners leveraging threat model
  mitigations (hash chain, RBAC, dry-run).
- **AOP-005**: Integrate agent workflows, async jobs, caching, and compliance
  harness as described in open questions.
