# Quickstart: OECD-Style Draft Authoring

Use this workflow when you want to author or review a draft AOP with explicit
OECD-style completeness checks before any publish planning.

## What this quickstart covers

- create a draft root AOP
- add key events with measurement, applicability, and optional `event_role` metadata
- record explicit KE essentiality judgments in the governed draft format
- add KER support text
- validate the draft with `validate_draft_oecd`, including draft topology checks
- optionally expose KE and KER polarity so `validate_draft_oecd` can perform directional concordance checks

## Important boundary

- `assess_aop_confidence` on live AOP-Wiki data is still heuristic for KE
  essentiality because the upstream RDF export does not expose a structured
  essentiality field.
- This quickstart covers the draft path instead: explicit KE-level
  `attributes.essentiality` metadata plus draft-graph topology that are
  validated locally.

## Step 1: create the draft root

Call `create_draft_aop` first.

```json
{
  "name": "create_draft_aop",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "title": "PXR activation leading to liver steatosis",
    "description": "Draft AOP assembled for OECD-style review.",
    "adverse_outcome": "Liver steatosis",
    "applicability": {
      "species": "human",
      "life_stage": "adult",
      "sex": "female"
    },
    "references": [
      {
        "title": "Example review reference"
      }
    ],
    "author": "researcher",
    "summary": "Create draft root"
  }
}
```

## Step 2: add key events

Use `add_or_update_ke` for each KE. Include measurement guidance and
applicability wherever you have it. Set `event_role` explicitly whenever you
know that a KE is the MIE, an intermediate event, or the AO; that gives
`validate_draft_oecd` deterministic topology anchors instead of inferred ones.
If the draft depends on directional biology, also set `attributes.direction_of_change`
when the KE title is not explicit enough for a conservative polarity inference.

Example with an explicit essentiality judgment:

```json
{
  "name": "add_or_update_ke",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "version_id": "v2",
    "author": "researcher",
    "summary": "Add upstream KE",
    "identifier": "KE:239",
    "title": "Activation, Pregnane-X receptor, NR1I2",
    "event_role": "mie",
    "attributes": {
      "measurement_methods": [
        "Reporter assay"
      ],
      "direction_of_change": "activation",
      "taxonomic_applicability": [
        "NCBITaxon:9606"
      ],
      "essentiality": {
        "evidence_call": "moderate",
        "rationale": "Blocking or attenuating this event reduced the downstream steatosis signal in the supporting studies curated for the draft.",
        "references": [
          {
            "identifier": "PMID:123456",
            "source": "pmid",
            "label": "Example essentiality reference"
          }
        ]
      }
    }
  }
}
```

Example when direct essentiality evidence has not been curated yet:

```json
{
  "name": "add_or_update_ke",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "version_id": "v3",
    "author": "researcher",
    "summary": "Add downstream KE",
    "identifier": "KE:459",
    "title": "Liver steatosis",
    "event_role": "ao",
    "attributes": {
      "measurement": "Histopathology",
      "essentiality": {
        "evidence_call": "not_assessed",
        "rationale": "Direct perturbation evidence has not yet been curated for this KE in the current draft.",
        "references": []
      }
    }
  }
}
```

## Governed essentiality format

`attributes.essentiality` must be an object with:

- `evidence_call`
- `rationale`
- optional `references`
- optional `provenance`

Allowed `evidence_call` values:

- `high`
- `moderate`
- `low`
- `not_reported`
- `not_assessed`

Anything outside that controlled vocabulary is rejected at write time.

## Step 3: add KER support

Use `add_or_update_ker` once the upstream and downstream KEs exist.

```json
{
  "name": "add_or_update_ker",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "version_id": "v4",
    "author": "researcher",
    "summary": "Add mechanistic relationship",
    "identifier": "KER:1",
    "upstream": "KE:239",
    "downstream": "KE:459",
    "plausibility": "Strong mechanistic rationale linking sustained PXR activation to downstream lipid accumulation.",
    "attributes": {
      "relationship_effect": "increased",
      "empirical_support": "Dose concordance observed in the curated studies.",
      "quantitative_understanding": "Moderate quantitative support."
    }
  }
}
```

## Step 4: validate the draft

Run `validate_draft_oecd` before review.

```json
{
  "name": "validate_draft_oecd",
  "arguments": {
    "draft_id": "draft-steatosis-1"
  }
}
```

Pay attention to:

- `ke_essentiality_shape`
- `ke_essentiality_coverage`
- `ke_event_role_coverage`
- `ke_measurement_coverage`
- `ke_applicability_coverage`
- `ker_plausibility_coverage`
- `ker_empirical_support_coverage`
- `ker_quantitative_support_coverage`
- `topology_anchor_inference_used`
- `topology_mie_present`
- `topology_ao_present`
- `topology_cycle_free`
- `topology_mie_to_ao_path_exists`
- `topology_anchor_degree_consistency`
- `topology_unanchored_key_events`
- `topology_directional_concordance_assessable`
- `topology_directional_concordance`
- `ker_assay_cutoff_ordering_assessable`
- `ker_assay_cutoff_ordering`

Explicit `not_assessed` or `not_reported` still count as essentiality
coverage, as long as the governed object is present with a rationale.

## Step 5: build a unified draft review bundle

When you want one review artifact instead of several separate tool calls, use
`review_draft_bundle`.
The bundle now includes the structured `evidence_gaps` payload and `evidence_gap_summary` directly, so it can serve as the default in-memory review object before export.

```json
{
  "name": "review_draft_bundle",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "assay_limit": 5,
    "stressor_limit": 10,
    "min_hitcall": 0.9
  }
}
```

If you also want one chemical projected onto the draft in the same response,
include `dtxsid`, `cas`, `inchikey`, or `name`.

If instead you want the same draft review signals reorganized as concrete
missing-data items, call `review_draft_evidence_gaps`.

```json
{
  "name": "review_draft_evidence_gaps",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "assay_limit": 5,
    "stressor_limit": 10,
    "min_hitcall": 0.9
  }
}
```

Look for:

- `global_gaps`
- `key_events[*].gaps`
- `relationships[*].gaps`
- `stressors[*].gaps`
- `recommendations`

## Step 6: inspect detailed draft quantitative ordering

When `validate_draft_oecd` reports draft KER assay-cutoff ordering as
assessable, use `review_draft_assay_cutoff_ordering` to inspect the actual
per-KER evidence.

```json
{
  "name": "review_draft_assay_cutoff_ordering",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "assay_limit": 5,
    "stressor_limit": 10,
    "min_hitcall": 0.9
  }
}
```

Look for:

- `summary.assessable_relationship_count`
- `relationships[*].assay_cutoff_ordering_call`
- `relationships[*].assay_cutoff_ordering.supporting_chemicals`
- `limitations`

## Step 7: export a review artifact

When you want a handoff-ready document, use `export_draft_review_artifact`.

```json
{
  "name": "export_draft_review_artifact",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "format": "markdown",
    "artifact_profile": "publication",
    "assay_limit": 5,
    "stressor_limit": 10,
    "min_hitcall": 0.9
  }
}
```

Use `format: "markdown"` for scientist-facing review notes and `format: "json"`
when another system needs the bundle serialized as an artifact payload. Use
`artifact_profile: "publication"` when you want a more structured report with
an executive summary, grouped findings, evidence tables, evidence-gap sections,
and recommended next actions.

The JSON export now carries both the unified draft review bundle and a
structured `evidence_gaps` block, so downstream systems do not have to scrape
the Markdown artifact to recover the gap analysis.

## Step 8: save the review artifact locally

When you want the rendered artifact written to disk for downstream handoff, use
`save_draft_review_artifact`.

```json
{
  "name": "save_draft_review_artifact",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "format": "markdown",
    "artifact_profile": "publication",
    "subdirectory": "handoff/steatosis",
    "filename": "scientific_review.md",
    "assay_limit": 5,
    "stressor_limit": 10,
    "min_hitcall": 0.9
  }
}
```

By default, files are written under `AOP_MCP_ARTIFACT_OUTPUT_DIR` (default
`output/draft_reviews/`). Set `overwrite: true` only when you intentionally
want to replace an existing artifact file. The metadata sidecar written next to
the artifact preserves both the bundle summary and the evidence-gap summary for
later discovery and handoff.

## Step 9: list saved review artifacts

When you want to rediscover previously saved handoff files, use
`list_saved_draft_review_artifacts`.

```json
{
  "name": "list_saved_draft_review_artifacts",
  "arguments": {
    "draft_id": "draft-steatosis-1",
    "artifact_profile": "publication",
    "format": "markdown",
    "subdirectory": "handoff/steatosis",
    "limit": 10
  }
}
```

The listing uses metadata sidecars written by `save_draft_review_artifact` when
available and falls back to filesystem inference for older artifact files.

## Step 10: build a Linear handoff document

When the next review system is Linear, use
`plan_linear_draft_review_document` to produce a connector-ready document
payload.

```json
{
  "name": "plan_linear_draft_review_document",
  "arguments": {
    "artifact_relative_path": "handoff/steatosis/scientific_review.md",
    "project": "Toxicology Reviews",
    "icon": ":microscope:"
  }
}
```

You can also call it with `draft_id` instead of `artifact_relative_path` when
you want the handoff generated directly from a live publication-profile export
instead of a previously saved artifact file.

## Practical interpretation

- Use this workflow to capture explicit author judgments for draft review.
- Prefer explicit `event_role` values on all KEs before review so topology
  validation can anchor on authored intent instead of heuristics.
- Prefer explicit KE and KER polarity metadata when directionality matters so
  the validator can flag obvious sign contradictions instead of reporting the
  path as not assessable.
- Prefer draft stressor links with resolvable chemical metadata such as a
  recognizable label, CAS-like source value, or DTXSID-like source value when
  you want `validate_draft_oecd` to compare upstream and downstream assay
  cutoffs for authored KERs.
- Do not treat it as a replacement for live upstream essentiality data, because
  that field is still absent in the current AOP-Wiki RDF export.
- Keep rationale and references explicit. The governed object is most useful
  when reviewers can trace exactly why a KE was marked `moderate` versus
  `not_assessed`.
