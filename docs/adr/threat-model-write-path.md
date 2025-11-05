# Threat Model — Write Path Extensions

## Scope
Covers new write-surface capabilities introduced for AOP MCP beyond PBPK read tooling:
- Draft store persisting proposed AOP/KE/KER updates.
- MCP tools for draft editing and validation.
- Publish planners generating MediaWiki edit scripts and AOPOntology OWL deltas.
- MediaWiki/AOPOntology execution flows (dry-run and eventual publish).

## Assets & actors
- **Assets**: Draft content, provenance/audit logs, MediaWiki credentials, AOPOntology deltas, publish plans, hash chain integrity.
- **Actors**: Authors (create drafts), reviewers (validate), publishers (execute), MCP service components, upstream operators, malicious actors.

## Trust boundaries
1. MCP tool surface ↔ authenticated user (MCP client or agent).
2. Tool layer ↔ draft store / job service.
3. Tool layer ↔ external MediaWiki/AOPOntology endpoints.
4. Semantic services ↔ ontology/ID minting data.
5. Async job queue ↔ workers processing long-running operations.

## STRIDE analysis

| Threat | Description | Impact | Mitigations |
|--------|-------------|--------|-------------|
| Spoofing | Impersonation of publisher role to execute write plan | Unauthorized edits to AOP-Wiki/AOPOntology | Enforce RBAC with signed JWT issued by auth service; require explicit publisher role; log all role assertions with hash chain reference |
| Tampering | Draft content or publish plan altered without provenance | Loss of trust in edits, potential data corruption | Draft store writes include PROV-O provenance + immutable hash of prior version; diff engine signs changes; audit log stored append-only |
| Repudiation | Actors deny initiating edits or approvals | Compliance breach | Hash-chained audit records tying tool call, user ID, timestamp, and payload digest; MediaWiki token responses stored with audit entry |
| Information disclosure | Leakage of unpublished drafts or credentials | Reputational/legal risk | Encrypt secrets at rest, scope draft store access to author/reviewer roles, redact sensitive fields in logs, use dedicated secret storage for MediaWiki/AOPO credentials |
| Denial of service | Abuse of write tools to overload upstream or queue | Prevents legitimate publishing | Rate-limit write tool invocations per user, guard async queue size, detect repeated validation failures; circuit-break on upstream 5xx |
| Elevation of privilege | Reviewer escalates to publisher without approval | Unauthorized publish | Require manual role assignment by ops; tool layer enforces hierarchical approval (draft validated -> publish); add dual-control for production MediaWiki endpoint |

## Additional mitigations
- **CSRF handling**: MediaWiki publish flow fetches fresh CSRF token per session; discard after use; verify token origin before accepting response.
- **Dry-run default**: Publish tools return plan JSON/OWL without executing live writes; only publisher role with explicit `execute=true` flag can trigger apply.
- **Validation hooks**: `validate_draft` enforces ontology constraints and reference checks prior to generating publish plan, reducing invalid edits.
- **Monitoring**: Metrics emit counts for validation failures, publish attempts, and rollback operations; alerts on anomaly thresholds.
- **Rollback readiness**: Maintain script to revert MediaWiki edits and remove AOPOntology delta if post-publish review fails; document procedure in publish quickstart.

## Residual risks & follow-up
1. Compromise of publisher credentials outside MCP still allows direct MediaWiki edits — maintain separate audit of credential use and rotate quarterly.
2. AOPOntology delta ingestion currently manual; need coordinated checklist with ontology maintainers to ensure provenance metadata accepted.
3. Async job queue persistence choice (TBD) must support at-least-once semantics without replaying publish jobs accidentally.
4. Evaluate need for additional transport encryption or VPN for AOPOntology store if exposed beyond internal network.

