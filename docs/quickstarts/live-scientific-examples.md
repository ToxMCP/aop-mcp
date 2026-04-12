# Quickstart: Live Scientific Examples

This guide captures a few concrete MCP calls that were validated against a live
server on `2026-04-12`. Treat them as reproducible starting points for review,
not as fixed benchmark outputs. Upstream AOP-Wiki, AOP-DB, and CompTox content
can change over time.

## 1. Search for steatosis pathways

Start broad with a phenotype query:

```json
{
  "name": "search_aops",
  "arguments": {
    "text": "liver steatosis",
    "limit": 5
  }
}
```

In the live validation run, this surfaced a plausible steatosis-centered
shortlist including `AOP:591`, `AOP:517`, `AOP:529`, and `AOP:518`.

Use this first call to decide whether you want:

- pathway inspection with `get_aop`, `list_key_events`, and `list_kers`
- assay aggregation with `list_assays_for_query`
- orphan discovery with `discover_orphan_stressors_for_query`

## 2. Review a KE with structured gene resolution

`KE:239` is a good live example of the improved KE assay search flow:

```json
{
  "name": "search_assays_for_key_event",
  "arguments": {
    "key_event_id": "KE:239",
    "limit": 5
  }
}
```

During live validation on `2026-04-12`, the server:

- read structured `gene_identifiers` from AOP-Wiki
- resolved `HGNC:1663` to `CD36`
- resolved `HGNC:7968` to `NR1I2`
- merged those structured symbols with the heuristic alias `PXR`
- ranked `TOX21_PXR_LUC_Agonist` first

This is the intended behavior for receptor-centered KEs where the wiki record
has structured gene identifiers and the title still contains useful domain
aliases.

## 3. Discover orphan stressors for a chemistry-linked AOP

`AOP:529` is the most useful live orphan-discovery example because it has linked
stressors and a non-empty assay layer:

```json
{
  "name": "discover_orphan_stressors_for_aop",
  "arguments": {
    "aop_id": "AOP:529",
    "assay_limit": 1,
    "per_assay_chemical_limit": 1,
    "limit": 3,
    "min_hitcall": 0.9
  }
}
```

In the warmed live-server validation run on `2026-04-12`, this returned one
candidate:

- `DTXSID4020248`
- supported by assay `BSK_3C`

Interpret this as a mechanistic lead rather than a causal claim. The tool is
designed to surface chemicals that are active in the strongest pathway assays
but are not already curated as linked AOP stressors.

## 4. Use query-driven orphan discovery for triage

When you want the server to choose a small set of relevant pathways first:

```json
{
  "name": "discover_orphan_stressors_for_query",
  "arguments": {
    "query": "liver steatosis",
    "search_limit": 3,
    "aop_limit": 1,
    "per_aop_limit": 1,
    "per_assay_chemical_limit": 1,
    "limit": 3,
    "min_hitcall": 0.9
  }
}
```

In the live run on `2026-04-12`, this selected `AOP:591` and returned no orphan
candidates because the selected pathway had `no_bioactivity_hits_after_filtering`.

That is still a useful result. It means:

- the phenotype search matched relevant AOPs
- the pathway selection logic worked
- the assay layer was too weak under the current `min_hitcall` threshold

## 5. Interpret a confidence review that disagrees with the narrative evidence

`AOP:529` is also a good example of why the new supplemental signals matter:

```json
{
  "name": "assess_aop_confidence",
  "arguments": {
    "aop_id": "AOP:529"
  }
}
```

In the live validation run on `2026-04-12`:

- `overall_call` was `low`
- `supplemental_signals.aop_level_evidence_signal.heuristic_call` was `strong`
- `supplemental_signals.assay_cutoff_ordering_signal.heuristic_call` was `low`
- the assay-cutoff ordering summary reported `5` concordant KERs and `4`
  discordant KERs across `9` shared-chemical comparisons

This is exactly the kind of scientifically useful tension the newer review layer
is meant to expose. The narrative evidence can look strong while the
assay-derived ordering still raises skepticism about pathway consistency.

## Suggested sequence

For a real review session, use the tools in this order:

1. `search_aops`
2. `get_aop`
3. `list_key_events` and `list_kers`
4. `search_assays_for_key_event` for high-value KEs
5. `assess_aop_confidence`
6. `discover_orphan_stressors_for_aop` or `discover_orphan_stressors_for_query`

If you are authoring rather than only reviewing, move next into:

1. `review_draft_bundle`
2. `review_draft_evidence_gaps`
3. `export_draft_review_artifact`
4. `save_draft_review_artifact`
