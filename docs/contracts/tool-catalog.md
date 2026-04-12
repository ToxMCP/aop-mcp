# AOP MCP Tool Catalog

Current MCP tool surface exposed by `POST /mcp`.

## Read tools

- `search_aops`: Search Adverse Outcome Pathways by text query with ranked title, synonym, and abstract matching.
- `get_aop`: Fetch a single AOP and its core metadata by AOP identifier.
- `get_key_event`: Fetch a single key event with enriched OECD-style metadata fields.
- `list_key_events`: List key events for a selected AOP.
- `get_ker`: Fetch a single key event relationship with plausibility, empirical support, quantitative understanding text, supplemental citation-concordance and assay-cutoff ordering heuristics for local KER review, and conservative KER applicability inference that can fall back to a lowest common taxon when exact species overlap is absent.
- `list_kers`: List key event relationships for a selected AOP.
- `get_related_aops`: Find AOPs related to a source AOP through shared key events or shared KERs.
- `assess_aop_confidence`: Build a partial OECD-aligned heuristic confidence summary from KE/KER evidence text, plus supplemental AOP-level evidence, KER citation-concordance context, and supplemental assay-cutoff ordering context derived from linked stressors and KE assay candidates.
- `find_paths_between_events`: Find directed KE/KER paths between two events within a selected AOP.
- `map_chemical_to_aops`: Map a chemical identifier to related AOPs using AOP-DB and CompTox.
- `map_assay_to_aops`: Given an assay identifier, return related AOPs. Do not pass AOP IDs.
- `list_assays_for_aop`: Resolve assay candidates for one AOP from linked stressor chemicals and CompTox bioactivity, with diagnostics explaining empty results and specificity-aware discovery ranking.
- `get_assays_for_aop`: Alias for `list_assays_for_aop` when you already have one AOP identifier and want assays.
- `discover_orphan_stressors_for_aop`: Start from one AOP's strongest assay candidates, pull active assay chemicals from CompTox, exclude already curated AOP stressors conservatively by DTXSID, CAS RN, and normalized name when possible, and return orphan mechanistic chemical candidates with diagnostics.
- `discover_orphan_stressors_for_aops`: Aggregate orphan chemical candidates across multiple AOPs, exclude chemicals already curated anywhere in the selected AOP set, preserve per-AOP diagnostics, and rank the remaining chemicals by cross-AOP support before single-pathway strength.
- `search_assays_for_key_event`: Rank CompTox assays from gene and phrase terms derived from a selected key event, with best-effort HGNC-backed resolution for structured `gene_identifiers`, direct CTX gene lookup, full-assay phrase search, narrow phenotype synonym expansion for phrase-only events, title-biased term extraction, alias expansion, taxonomic preference hints, and AOP-Wiki fallback extraction.
- `list_assays_for_aops`: Aggregate and deduplicate assay candidates across multiple AOPs, with per-AOP diagnostics for empty results and specificity-aware discovery ranking.
- `get_assays_for_aops`: Alias for `list_assays_for_aops` when you already have a list of AOP identifiers and want assays.
- `list_assays_for_query`: Search AOPs by phenotype or mechanism query and aggregate assay candidates for the selected AOP set, with query and per-AOP diagnostics.
- `discover_orphan_stressors_for_query`: Search AOPs by phenotype or mechanism query, select the top AOPs, and aggregate orphan chemical candidates across that selected set with query and per-AOP diagnostics.
- `export_assays_table`: Export aggregated assay candidates as `csv` or `tsv` from either a query or explicit AOP list.
- `review_draft_assay_cutoff_ordering`: Review one draft's per-KER assay-cutoff ordering evidence by combining draft stressor links, KE assay candidates, and CompTox bioactivity cutoffs.
- `review_draft_bundle`: Build a unified draft review bundle that combines `validate_draft_oecd`, detailed draft assay-cutoff ordering review, structured evidence-gap findings, and optional chemical projection into one response.
- `review_draft_evidence_gaps`: Mine one draft for concrete evidence gaps across root metadata, topology, KE assay coverage, KER evidence fields, and linked stressor resolvability.
- `export_draft_review_artifact`: Export the unified draft review bundle as scientist-facing markdown or json for downstream review workflows, with a `publication` markdown profile for more structured handoff reports and evidence-gap sections derived from the draft gap miner. JSON exports now include a structured `evidence_gaps` block alongside the bundle.
- `list_saved_draft_review_artifacts`: List saved local draft review artifacts from the configured artifact output directory, with optional draft, profile, format, and subdirectory filters.
- `plan_linear_draft_review_document`: Build a connector-ready Linear document payload from either a live draft review export or a saved local review artifact, with both bundle and evidence-gap summaries surfaced in the response.
- `save_draft_review_artifact`: Render and persist a draft review artifact to the local artifact output directory, with optional subdirectory and filename override support. Metadata sidecars now also preserve an evidence-gap summary for discovery and handoff tools.
- `trace_chemical_on_draft`: Resolve one chemical to a CompTox DTXSID, map each draft key event to candidate assays, and return a draft KE/KER overlay showing which draft nodes have matching chemical bioactivity.
- `get_applicability`: Normalize applicability parameters such as species, sex, and life stage.
- `get_evidence_matrix`: Build an evidence matrix from KER facets.

## Write tools

- `create_draft_aop`: Create a new draft AOP for write-path workflows.
- `add_or_update_ke`: Add or update a key event within a draft, including governed KE-level `essentiality` metadata and optional `event_role` metadata (`mie`, `intermediate`, `ao`) when available.
- `add_or_update_ker`: Add or update a key event relationship within a draft.
- `link_stressor`: Link a stressor to a draft entity.
- `validate_draft_oecd`: Validate a draft against OECD AOP handbook-style completeness expectations, including governed KE-level `essentiality` coverage and shape checks plus draft-graph topology checks for anchors, cycles, and MIE -> AO reachability.
- `validate_draft_oecd` also performs conservative directional concordance checks on draft MIE -> AO paths when the draft exposes enough KE and KER polarity metadata to assess them.
- `validate_draft_oecd` also performs supplemental draft KER assay-cutoff ordering checks when draft stressor links can be resolved to CompTox chemicals and the drafted KEs map to assay candidates with evaluable cutoffs.
- Use `review_draft_bundle` when you want the default scientist-facing draft review package instead of stitching the validator, evidence-gap review, quantitative review, and optional chemical trace together yourself.
- Use `review_draft_evidence_gaps` when you want an action-oriented gap report instead of a raw bundle. It groups missing review evidence by root metadata, key event, relationship, and stressor.
- Use `export_draft_review_artifact` when that same bundle needs to be handed off as markdown or json rather than returned as a raw MCP review object. The markdown profiles now include evidence-gap sections and next actions derived from `review_draft_evidence_gaps`, and the JSON export now carries a structured `evidence_gaps` block alongside the review bundle. Use `artifact_profile: "publication"` when you want a more polished scientist-facing report layout instead of the default review-style markdown.
- Use `list_saved_draft_review_artifacts` when you need to discover or filter previously saved review files without browsing the output directory manually.
- Use `plan_linear_draft_review_document` when the next handoff target is Linear or another document system that expects a document title plus markdown body instead of a raw artifact payload. The response now preserves both the exported bundle summary and the evidence-gap summary.
- Use `save_draft_review_artifact` when the exported review needs to become a real local handoff file under `AOP_MCP_ARTIFACT_OUTPUT_DIR` instead of staying in-memory as an MCP response payload. The metadata sidecar written next to the file preserves both the bundle summary and the evidence-gap summary.
- Use `review_draft_assay_cutoff_ordering` when you want the detailed per-KER assay-cutoff ordering objects behind those draft quantitative checks instead of only the validator status/message pair.
- `trace_chemical_on_draft` is a draft-review helper. It highlights draft key events using assay matches plus CompTox bioactivity for one chemical, but it does not establish causal directionality or prove that the chemical traverses the full drafted pathway.
- For directional draft validation, KE polarity can be inferred from titles like `Activation, ...` or `Decreased, ...`, but drafts are more reliably assessable when authors set explicit KE fields such as `attributes.direction_of_change` and KER fields such as `attributes.relationship_effect`.
- For draft quantitative-ordering validation, link stressors with resolvable chemical metadata whenever possible. A recognizable label, CAS-like source value, or DTXSID-like source value makes the assay-cutoff ordering checks more likely to be assessable.

## Notes

- Tool schemas are exposed through MCP `tools/list` and validated by the server before tool execution.
- Response contracts live under `docs/contracts/schemas/`.
- Use `search_aops` for discovery and `get_aop` for fetching a known identifier.
- Assay tool routing:
  - assay -> AOPs: `map_assay_to_aops`
  - AOP -> assays: `get_assays_for_aop`, `get_assays_for_aops`
  - AOP -> orphan chemical candidates: `discover_orphan_stressors_for_aop`
  - multiple AOPs -> cross-pathway orphan chemical candidates: `discover_orphan_stressors_for_aops`
  - phenotype/query -> assays: `list_assays_for_query`
  - phenotype/query -> orphan chemical candidates: `discover_orphan_stressors_for_query`
  - key event -> candidate assays: `search_assays_for_key_event`
- Use `search_assays_for_key_event` as a first-pass KE/MIE assay search; it is KE-derived target matching rather than a curated ontology mapping. Structured HGNC identifiers are resolved into gene symbols when possible and merged with heuristic KE parsing before CTX gene lookup. Phrase-only KEs search the full CTX assay metadata set with a narrow phenotype synonym layer before falling back to AOP-Wiki measurement methods. Returned assay ranking is specificity-aware discovery ranking, not a mechanistic truth claim.
- `discover_orphan_stressors_for_aop` is a discovery helper. It surfaces uncurated chemicals that are active in an AOP's strongest assays, but it does not prove pathway traversal, causal sufficiency, or regulatory relevance.
- `discover_orphan_stressors_for_aops` is also a discovery helper. Cross-AOP recurrence can be useful prioritization context, but it still does not prove shared causal traversal or establish regulatory confidence.
- `discover_orphan_stressors_for_query` adds an AOP-search selection layer on top of that same workflow. Its output depends on both the query-to-AOP matching quality and the downstream orphan-discovery evidence.
- `get_key_event` and `search_assays_for_key_event` advertise `key_event_id` in MCP `tools/list`; legacy `ke_id` input remains accepted for compatibility.
- In `assess_aop_confidence`, OECD core dimensions are exposed under `confidence_dimensions`; AOP-level free-text evidence is reported separately under `supplemental_signals`.
- `get_ker.citation_concordance` and `assess_aop_confidence.supplemental_signals.citation_concordance_signal` are reference-overlap heuristics only. Shared citations can be useful review context, but they are not treated as proof that the same experiment measured both events together.
- `get_ker.assay_cutoff_ordering` and `assess_aop_confidence.supplemental_signals.assay_cutoff_ordering_signal` are supplemental quantitative-ordering heuristics. They compare best observed CompTox activity cutoffs across upstream/downstream KE assay candidate sets for shared linked stressor chemicals, but they are not treated as curated qAOP models or OECD core dimensions.
- `get_ker.applicability.taxa` still prefers exact upstream/downstream taxon overlap. Lowest-common-ancestor inference is only used as a fallback for known taxon lineages and is intentionally blocked from collapsing all the way to very broad ancestors such as `Metazoa` or `Eukaryota`.
