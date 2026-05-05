# Changelog

## Unreleased

### Added

- Machine-readable trust evaluation Q/A pack for auditability, verifiability, Registry handoff trust, replay reproducibility, scientific value, and regulatory-boundary checks.
- Tighter MCP tool annotations for write-scope enforcement, live/open-world draft review helpers, and read-only export hints.

## v0.9.0 - 2026-05-05

### Added

- Registry handoff review and draft-attachment tools for imported `aop_context` support bundles.
- External Registry support summaries in draft review bundles, saved artifacts, and replay packages.
- Central MCP tool-call audit records with schema validation, policy status, scopes, request/response hashes, and output-schema hashes.
- Optional durable MCP tool-call audit JSONL logging through `AOP_MCP_AUDIT_LOG_PATH`.
- `verify_tool_call_audit_log` for durable JSONL hash-chain verification.
- `list_tool_call_audit_records` for recent process-local MCP audit inspection.
- `export_tool_call_audit_log_evidence` for bounded, chain-verified durable audit evidence export with verified-prefix behavior on tamper.
- `export_draft_replay_package` runtime manifests with server/runtime/config posture, schema-root hash, selected response-schema hashes, tool-catalog hash, and best-effort git commit.
- Trust and auditability documentation plus stable read-only trust evaluation scenarios.

### Notes

- The v0.9.0 trust surface is intended for research-grade auditability, reproducibility, and scientific review support.
- Regulatory-grade controls such as immutable external retention, independent timestamping, validated e-signature workflows, formal RBAC approval gates, and deployment-specific retention policy remain out of scope.

## v0.8.2 - 2026-04-16

### Added

- Hardened SPARQL query construction with safe template rendering.
- Per-endpoint circuit-breaker resilience for upstream SPARQL calls.
- Strengthened draft graph audit-chain checks and electronic-signature metadata.
- Ontology drift protection scaffold with configurable CURIE resolution and ontology migration helpers.

## v0.8.1

### Added

- Expanded scientific review surface for assay ranking, KE assay search, KER citation concordance, taxonomic applicability inference, draft topology validation, directional concordance checks, and supplemental assay-cutoff ordering review.
- Draft review workflow covering bundle review, evidence-gap review, artifact export/save/list, and Linear-ready document planning.
- Orphan stressor discovery across one AOP, multiple AOPs, and phenotype or mechanism queries.
