# Quickstart: OECD-Style Draft Authoring

Use this workflow when you want to author or review a draft AOP with explicit
OECD-style completeness checks before any publish planning.

## What this quickstart covers

- create a draft root AOP
- add key events with measurement and applicability metadata
- record explicit KE essentiality judgments in the governed draft format
- add KER support text
- validate the draft with `validate_draft_oecd`

## Important boundary

- `assess_aop_confidence` on live AOP-Wiki data is still heuristic for KE
  essentiality because the upstream RDF export does not expose a structured
  essentiality field.
- This quickstart covers the draft path instead: explicit KE-level
  `attributes.essentiality` metadata that is validated locally.

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
applicability wherever you have it.

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
    "attributes": {
      "measurement_methods": [
        "Reporter assay"
      ],
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
- `ke_measurement_coverage`
- `ke_applicability_coverage`
- `ker_plausibility_coverage`
- `ker_empirical_support_coverage`
- `ker_quantitative_support_coverage`

Explicit `not_assessed` or `not_reported` still count as essentiality
coverage, as long as the governed object is present with a rationale.

## Practical interpretation

- Use this workflow to capture explicit author judgments for draft review.
- Do not treat it as a replacement for live upstream essentiality data, because
  that field is still absent in the current AOP-Wiki RDF export.
- Keep rationale and references explicit. The governed object is most useful
  when reviewers can trace exactly why a KE was marked `moderate` versus
  `not_assessed`.
