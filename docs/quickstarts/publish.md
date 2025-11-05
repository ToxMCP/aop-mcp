# Draft to Publish Workflow

This quickstart outlines how to stage edits, review them, and generate publish plans for
MediaWiki and AOPOntology without executing live writes.

## Roles & RBAC
- **Author** – creates drafts and edits key events/relationships.
- **Reviewer** – validates drafts, checks for consistency, and approves readiness for publish.
- **Publisher** – executes publish plans against MediaWiki/AOPOntology after review.

Ensure your MCP environment issues JWTs with the appropriate role claims before invoking write
or publish tools. The publish operations remain dry-run until an explicit execution step is
implemented.

## Draft lifecycle
1. `create_draft_aop` – establish a new draft with baseline metadata and applicability.
2. `add_or_update_ke`/`add_or_update_ker` – evolve the draft graph, reusing existing nodes when
   possible.
3. `link_stressor` – attach stressor references with provenance metadata.
4. Repeat edits until the draft captures the intended changes.

All write tools respond with the draft ID and latest version so reviewers can track progress.

## Validation & review
- Use semantic tools (`get_applicability`, `get_evidence_matrix`) to confirm ontology alignment.
- Extend the draft store with validation routines (e.g., cycle checks, schema guards) before
  permitting reviewers to approve.
- Store reviewer notes in the draft metadata or external ticketing system.
- Run the compliance checklist (`docs/contracts/compliance/checklist.md`) to ensure audit chain,
  RBAC, and telemetry requirements are satisfied prior to publish.

## Publish planning
1. Fetch the latest draft and version from the draft store service.
2. Generate a MediaWiki plan:
   ```python
   from src.services.publish import MediaWikiPublishPlanner
   planner = MediaWikiPublishPlanner()
   plan = planner.build_plan(draft, version)
   print(plan.to_dict())
   ```
3. Generate an OWL delta:
   ```python
   from src.services.publish import OWLPublishPlanner
   planner = OWLPublishPlanner()
   delta = planner.build_delta(draft, version)
   print(delta.to_dict())
   ```
4. Share the dry-run artifacts with reviewers and publishers. Plans include page summaries,
   key event listings, and OWL individual/property changes.

## Execution (future work)
- The publish planner outputs are intended for downstream executors responsible for CSRF token
  management (MediaWiki) and OWL API interactions.
- Implement `propose_publish` and `publish` tools to enforce RBAC, capture audit logs, and apply
  the generated plans when ready.

## Rollback guidance
- Retain prior draft versions and publish plans so you can revert to a known state if a live
  publish introduces issues.
- For MediaWiki, generate follow-up plans that restore previous content. For OWL, maintain delta
  history to reverse individual/property updates.
