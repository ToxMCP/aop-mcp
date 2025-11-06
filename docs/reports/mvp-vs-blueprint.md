# Implementation Strategy: MVP read-only vs. full blueprint

## Recommendation

- **Adopt the read-only MVP first** (stabilize adapters + MCP contract)
  - Offline fixture fallback now ensures the MCP remains usable even without SPARQL reachability.
  - Contract + smoke suites cover every read/write schema.
  - Endpoint health script highlights live outages without blocking local workflows.
- After MVP hardening, incrementally layer write-path and advanced features (publish planners, audit chain, LangGraph workflows).

## Decision drivers

| Driver | MVP read-only | Full blueprint |
| --- | --- | --- |
| External dependency risk | Mitigated via fixture fallback and CI health checks | Requires stable MediaWiki/AOPO endpoints and auth |
| Time to usable MCP | Immediate, tools callable offline | High (MediaWiki + OWL exporters, RBAC, audit) |
| Testing footprint | Current suites + live endpoint smoke | Needs additional integration harness (publish diff, provenance) |
| Team bandwidth | Supports parallel write-path investment later | Demands cross-team coordination (Wiki ops, ontology team) |

## Next steps

1. Run `make check-endpoints` in a network-enabled environment and capture live samples under `tests/golden/live/` for regression tracking.
2. Ship the read-only MVP (search, get, list, semantic helpers) to unblock agent integrations.
3. Plan the write-path increments:
   - MediaWiki publish planner execution + CSRF choreography.
   - OWL export validation + PROV-O hooks.
   - RBAC + audit chain enforcement.
4. Revisit blueprint milestones once read-path telemetry confirms usage patterns.

