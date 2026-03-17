# AOP MCP Tool Catalog

Current MCP tool surface exposed by `POST /mcp`.

## Read tools

- `search_aops`: Search Adverse Outcome Pathways by text query with ranked title, synonym, and abstract matching.
- `get_aop`: Fetch a single AOP and its core metadata by AOP identifier.
- `get_key_event`: Fetch a single key event with enriched OECD-style metadata fields.
- `list_key_events`: List key events for a selected AOP.
- `get_ker`: Fetch a single key event relationship with plausibility, empirical support, and quantitative understanding text.
- `list_kers`: List key event relationships for a selected AOP.
- `get_related_aops`: Find AOPs related to a source AOP through shared key events or shared KERs.
- `assess_aop_confidence`: Build a partial OECD-aligned heuristic confidence summary from KE/KER evidence text, plus supplemental AOP-level context.
- `find_paths_between_events`: Find directed KE/KER paths between two events within a selected AOP.
- `map_chemical_to_aops`: Map a chemical identifier to related AOPs using AOP-DB and CompTox.
- `map_assay_to_aops`: Map an assay identifier to related AOPs.
- `list_assays_for_aop`: Resolve assay candidates for one AOP from linked stressor chemicals and CompTox bioactivity.
- `search_assays_for_key_event`: Rank CompTox assays from gene and phrase terms derived from a selected key event, with title-biased term extraction, alias expansion, taxonomic preference hints, and AOP-Wiki fallback extraction.
- `list_assays_for_aops`: Aggregate and deduplicate assay candidates across multiple AOPs.
- `list_assays_for_query`: Search AOPs by phenotype or mechanism query and aggregate assay candidates for the selected AOP set.
- `export_assays_table`: Export aggregated assay candidates as `csv` or `tsv` from either a query or explicit AOP list.
- `get_applicability`: Normalize applicability parameters such as species, sex, and life stage.
- `get_evidence_matrix`: Build an evidence matrix from KER facets.

## Write tools

- `create_draft_aop`: Create a new draft AOP for write-path workflows.
- `add_or_update_ke`: Add or update a key event within a draft.
- `add_or_update_ker`: Add or update a key event relationship within a draft.
- `link_stressor`: Link a stressor to a draft entity.
- `validate_draft_oecd`: Validate a draft against OECD AOP handbook-style completeness expectations.

## Notes

- Tool schemas are exposed through MCP `tools/list` and validated by the server before tool execution.
- Response contracts live under `docs/contracts/schemas/`.
- Use `search_aops` for discovery and `get_aop` for fetching a known identifier.
- Use `search_assays_for_key_event` as a first-pass KE/MIE assay search; it is KE-derived target matching rather than a curated ontology mapping.
- `get_key_event` and `search_assays_for_key_event` advertise `key_event_id` in MCP `tools/list`; legacy `ke_id` input remains accepted for compatibility.
- In `assess_aop_confidence`, OECD core dimensions are exposed under `confidence_dimensions`; AOP-level free-text evidence is reported separately under `supplemental_signals`.
