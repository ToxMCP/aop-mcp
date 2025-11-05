# Agent Workflow & Async Job Notes

## Goals
- Provide LangGraph-compatible workflow scaffolding to orchestrate discovery and publish flows.
- Introduce an async job service for long-running SPARQL queries, ingest, and publish execution.
- Keep planners and job submissions dry-run friendly to maintain parity with Phase D safety goals.

## Components
- **WorkflowFactory** (`src/agent/workflows.py`) builds preset workflows that combine semantic
  tools, write tooling, publish planners, and the job service.
- **JobService** (`src/services/jobs/`) exposes a backend-agnostic API for submitting jobs,
  updating status, and retrieving results. The included in-memory backend supports unit tests
  and local development.
- **Publish planners** feed workflow steps with dry-run MediaWiki and OWL payloads.

## Execution flow (publish example)
1. Generate dry-run plans for MediaWiki and OWL using the planners.
2. Enqueue a follow-on job responsible for executing the plans (or handing them off to an
   operator). The job remains in the queue until the publisher role confirms execution.
3. Future work: extend WorkflowFactory with confirmation prompts and RBAC checks before allowing
   queued jobs to execute.

## Open questions
- Integrate actual LangGraph library to leverage built-in planning/execution features once the
  MCP surface is finalized.
- Determine persistent backend (Redis/Postgres) for JobService when running in production and
  connect cache instrumentation to the chosen store. Structured logging is now emitted for drafts
  and job lifecycle events to support alerting pipelines.
- Add telemetry hooks to record workflow decisions and job outcomes for audit/compliance.
