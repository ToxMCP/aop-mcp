# Trust and Auditability Model

This document describes the current trust surface for AOP MCP as implemented in code and contracts. It is scoped to research-grade transparency and reproducibility support. It is not a claim of regulatory validation, compliant electronic records, or immutable third-party retention.

## What Is Auditable

- Draft versions carry graph checksums, provenance checksums, previous-version links, and optional signatures.
- Draft review bundles expose external Registry support summaries and bounded-use limitations when Registry handoff bundles are attached.
- Saved draft review artifacts include content and metadata hashes, plus verification status when they are listed or attached to a replay package.
- MCP tool calls are recorded in a bounded process-local audit buffer.
- When `AOP_MCP_AUDIT_LOG_PATH` is configured, MCP tool calls are also written to a durable JSONL log with a hash chain.
- Replay packages include draft integrity, external support, saved artifact integrity, recent audit records, audit persistence status, and a runtime manifest.

## Verification Tools

- `verify_tool_call_audit_log` verifies the durable JSONL audit-log hash chain from the configured path or an explicit local path.
- `list_tool_call_audit_records` lists recent process-local tool-call audit records with filters and persistence status.
- `export_tool_call_audit_log_evidence` exports a bounded, chain-verified durable audit-log evidence package. If the log is tampered, only the verified prefix before the first failure is exported.
- `export_draft_replay_package` packages a draft version, integrity status, Registry support, artifact verification, recent audit records, and a runtime manifest for reproducibility review.

## Runtime Manifest

Replay packages include `runtime_manifest` with:

- AOP MCP server name and package version.
- Python implementation, version, executable name, and platform string.
- Security-relevant configuration posture without secret values.
- Schema-root hash, selected response-schema hashes, tool count, tool names, and tool catalog hash.
- Best-effort git commit from the local checkout when available.

The manifest is included in `package_sha256`, so changes to the runtime, tool catalog, or schema contract alter the replay package fingerprint.

## Limits

- Process-local audit records are bounded and disappear when the server process restarts.
- Durable JSONL logging is optional and only active when `AOP_MCP_AUDIT_LOG_PATH` is configured.
- The durable hash chain detects in-file tampering, sequence drift, unsupported envelope versions, and content hash mismatch, but it does not provide independent timestamping or immutable external storage.
- Audit records store request and response hashes, argument keys, policy status, scopes, and validation status. They do not store raw request or response bodies.
- Git commit discovery is best effort and does not assess worktree dirtiness.
- Regulatory-grade controls such as validated retention policy, role-based production approval workflows, e-signature compliance, external timestamping, and immutable ledger storage remain out of scope for this implementation.

## Scientific Value

The trust surface is designed to help reviewers answer practical questions:

- Which draft version and graph checksum was reviewed?
- Which Registry bundles were attached, and what limitations came with them?
- Which MCP calls contributed to a replay package?
- Did the response schemas and tool catalog match the runtime that produced the package?
- Is the durable audit log intact up to the exported evidence boundary?

These checks support scientific review and reproducibility. They do not replace expert assessment of AOP biological plausibility, OECD evidence strength, or regulatory acceptance.
