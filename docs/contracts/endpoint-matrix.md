# Endpoint Matrix — AOP MCP Integrations

| Integration | Capability | Primary Endpoint (placeholder) | Failover / Mirror | Auth & Secrets | SLA / Rate Notes | Retry & Cache Guidance |
|-------------|------------|---------------------------------|-------------------|----------------|------------------|------------------------|
| AOP-Wiki SPARQL | Read AOP graph (search, get, list, find_paths) | `https://sparql.vhp4safety.nl/blazegraph/namespace/aopwikidb/sparql` | `https://api.openrisknet.org/aopwiki/sparql` | None (public); enforce user-agent header | Community mirror; subject to maintenance windows, prefer 30 qps max, monitor 429 | Use exponential backoff (base 0.5s, max 8s), circuit-break on 5xx after 3 tries; cache successful responses 5 min for read tools |
| AOP-DB SPARQL | Cross-domain joins (chemicals, assays, diseases) | `https://sparql.vhp4safety.nl/blazegraph/namespace/aopdb/sparql` | `https://api.openrisknet.org/aopdb/sparql` | None (public); optional API key if provided by operators | Similar policies to AOP-Wiki; expect higher latency for complex joins | Same retry policy; prefer async job path for `find_paths` > 2 hops; cache 10 min for chemical/assay maps |
| CompTox (DSSTox/CTS) | Map chemicals to stressors/AOPs | `https://comptox.epa.gov/dashboard/api/` | None — plan local fixture fallback | API key stored in `COMPTOX_API_KEY` secret; rate limited (~50 req/min) | Daily maintenance window 00:00–01:00 ET; 429 on burst | Retry twice on 429 with jitter (1s, 3s); cache positive hits 24h, negative 1h |
| MediaWiki Action API | Stage publish plans for AOP-Wiki | `https://aopwiki.rdf.tools/api.php` | `https://aopwiki.org/api.php` (production — use cautiously) | Auth via bot credentials (`AOP_MW_USERNAME`/`AOP_MW_PASSWORD`); CSRF token per session | Production API subject to edit limits; staging mirror resets nightly | Dry-run default; enforce RBAC so only publishers hit production; retry login/token flow twice before surfacing error |
| AOPOntology Triple Store | Generate OWL deltas for review/import | `https://ontology.aopkb.org/repositories/aopo` | Local GraphDB instance for validation | Basic auth (`AOPO_TRIPLESTORE_USER`/`AOPO_TRIPLESTORE_PASS`); write via authenticated context | Production updates coordinated with ontology maintainers; downtime announced via mailing list | Publish planner only produces deltas; execution requires manual approval; treat 5xx as fatal, do not auto-retry without operator input |
| Effectopedia Export (optional) | Package drafts for Effectopedia import | `file://exports/effectopedia/` | n/a | Local filesystem permissions | Manual run; no uptime guarantee | Generate on demand; ensure path writable and clean previous artifacts |

## Operational notes
- Store secrets in the Taskmaster deployment vault; never commit credentials.
- Health-check primary SPARQL endpoints hourly; switch to mirror after two consecutive failures and notify ops.
- Log upstream endpoint selection and latency to support tuning and failover audits.
- Document any additional mirrors in this matrix as they become available.

