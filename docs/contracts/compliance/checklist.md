# Compliance & Audit Harness Checklist

## Audit chain
- [ ] Verify each draft version has `checksum` and `previous_checksum` populated.
- [ ] Recompute graph checksums and confirm chain integrity.
- [ ] Ensure publish plans (MediaWiki/OWL) are stored with references to draft version and hash.

## RBAC enforcement
- [ ] Confirm write tools reject operations when role claims (author/reviewer/publisher) are missing.
- [ ] Validate publish workflow requires explicit publisher confirmation before execution.
- [ ] Check audit logs capture role assertions and tool invocations with correlation IDs.

## Logging & telemetry
- [ ] Structured logs include `draft_id`, `version_id`, and job IDs for every write/publish action.
- [ ] Metrics counters (`sparql.cache_hit`, `sparql.cache_miss`, job status transitions) are emitted and monitored.
- [ ] Alerts configured for repeated job failures or cache miss spikes.

## Documentation
- [ ] Quickstart guidance outlines review/publish responsibilities and rollback steps.
- [ ] ADRs reference compliance checks and outstanding open questions.
- [ ] Incident playbook defines procedure for reverting drafts and rolling back publish plans.

