# Trust Evaluation Scenarios

These stable, read-only scenarios are intended for human or agent evaluation of the AOP MCP trust surface. They avoid live network dependencies and use deterministic fixtures or locally generated draft/audit data.

The companion machine-readable pack in `docs/evaluations/trust-scenarios.xml` expands this set to ten string-checkable Q/A pairs covering auditability, verifiability, Registry handoff trust, replay reproducibility, scientific value, and regulatory boundaries.

## Scenario 1: Verify A Durable Audit Log

Question: Given a configured durable audit log with two valid MCP tool-call envelopes, can the agent prove the log is intact?

Expected tool path:

- Call `verify_tool_call_audit_log`.
- Confirm `chain.verified` is `true`.
- Confirm `chain.record_count` is `2`.
- Confirm `head_record_hash` is a 64-character lowercase hex digest.

Expected answer: The durable audit log is intact for two records, with the reported head hash as the current chain tip.

## Scenario 2: Detect Tampered Durable Evidence

Question: Given a durable audit log whose second JSONL envelope has been modified without updating `record_hash`, can the agent identify the verified boundary?

Expected tool path:

- Call `export_tool_call_audit_log_evidence` with a bounded `limit`.
- Confirm `chain.verified` is `false`.
- Confirm `verified_prefix_envelope_count` is `1`.
- Report the warning that mentions `record_hash does not match`.

Expected answer: The first envelope remains usable as the verified prefix; evidence at and after the tampered second envelope must not be treated as verified.

## Scenario 3: Explain Replay Package Reproducibility

Question: Given an exported draft replay package, can the agent identify the runtime and contract fingerprints that produced it?

Expected tool path:

- Call `export_draft_replay_package`.
- Inspect `runtime_manifest.server.version`.
- Inspect `runtime_manifest.contracts.schema_root_sha256`.
- Inspect `runtime_manifest.tool_registry.tool_catalog_sha256`.
- Inspect `draft_integrity.selected_version.graph_sha256`.

Expected answer: The replay package identifies the selected draft graph hash, the AOP MCP version, the response-schema root hash, and the tool-catalog hash used to produce the package.

## Scenario 4: Separate Scientific Review From Regulatory Claims

Question: Can the agent explain whether a verified replay package proves regulatory acceptance?

Expected tool path:

- Read `docs/trust-auditability.md`.
- Optionally inspect `limitations` in `export_draft_replay_package`.

Expected answer: No. The package supports auditability, reproducibility, and scientific review, but it does not prove regulatory acceptance or satisfy regulatory-grade records requirements by itself.
