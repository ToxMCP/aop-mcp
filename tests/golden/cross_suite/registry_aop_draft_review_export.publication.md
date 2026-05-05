# Scientific Draft Review: Registry-supported mechanistic context review

## Executive Summary
- Disposition: Ready for external scientific review
- Draft ID: draft-registry-aop-golden
- Version ID: v5
- Adverse outcome: Liver steatosis
- Validation score: 40
- Blocking validation findings: 0
- Non-blocking review warnings: 12
- Assessable quantitative KER reviews: 0
- Discordant quantitative KER reviews: 0
- Chemical activity overlay included: No

## Draft Context
| Field | Value |
| --- | --- |
| Draft title | Registry-supported mechanistic context review |
| Draft ID | draft-registry-aop-golden |
| Version ID | v5 |
| Adverse outcome | Liver steatosis |
| Key events in quantitative review scope | 2 |
| Relationships in quantitative review scope | 1 |
| Linked stressors | 0 |

## Review Findings
- Blocking findings: 0
- Advisory findings: 12
- Passed checks: 19

### Advisory Findings
- `title_format`: Use the form 'MIE leading to AO' or 'MIE leading to AO via distinctive KE' where possible.
- `applicability_present`: Add species / life stage / sex applicability metadata on the draft root.
- `references_present`: Add at least one reference supporting the AOP summary.
- `graphical_representation_present`: Store a diagram or reference to a graphical AOP representation on the root entity.
- `contact_present`: Add corresponding author / point-of-contact metadata for review workflows.
- `stressor_links`: Link one or more stressors where known; this is especially useful for MIE-centric review.
- `ke_applicability_coverage`: 1/2 key events include applicability metadata.
- `ke_essentiality_coverage`: 0/2 key events include governed essentiality metadata; explicit 'not_assessed' or 'not_reported' counts as coverage.
- `ker_empirical_support_coverage`: 0/1 KERs include empirical support content.
- `ker_quantitative_support_coverage`: 0/1 KERs include quantitative understanding content.
- `topology_directional_concordance_assessable`: No MIE-to-AO KER steps exposed enough polarity metadata to assess directional concordance. Add KE directionality (for example attributes.direction_of_change) and explicit KER effect metadata (for example attributes.relationship_effect).
- `ker_assay_cutoff_ordering_assessable`: CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived.

## Quantitative Evidence
| Metric | Value |
| --- | ---: |
| Searchable stressors | 0 |
| Assessable relationships | 0 |
| Concordant relationships | 0 |
| Discordant relationships | 0 |
| Supporting chemical observations | 0 |

| Relationship | Call | Supporting chemicals | Basis |
| --- | --- | ---: | --- |
| KER:1 (KE:1 -> KE:2) | not_reported | 0 | CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived. |

## Evidence Gaps
| Gap scope | Count |
| --- | ---: |
| Total gaps | 15 |
| Blocking gaps | 0 |
| Advisory gaps | 15 |
| Global gaps | 8 |
| Key event gaps | 4 |
| Relationship gaps | 3 |
| Stressor gaps | 0 |
| KE assay-mapping gaps | 1 |

### Key Event Gap Hotspots
| Key event | Gap count | Missing items |
| --- | ---: | --- |
| KE:1 (Activation, Pregnane-X receptor, NR1I2) | 1 | Key event is missing explicit essentiality metadata |
| KE:2 (Liver steatosis) | 3 | Key event is missing applicability metadata; Key event is missing explicit essentiality metadata; No candidate assays were found for this key event |

### Relationship Gap Hotspots
| Relationship | Gap count | Missing items |
| --- | ---: | --- |
| KER:1 (KE:1 -> KE:2) | 3 | KER is missing empirical support evidence; KER is missing quantitative understanding; Assay cutoff ordering is not assessable for this KER |

## Chemical Activity Overlay
- No chemical activity overlay was requested for this artifact.

## External Support
- Attached Registry bundles: 1
- Review-ready imported bundles: 1
- Imported evidence items: 2
- Bounded-use warnings: 1
- Scientific-review flags: 2
- Blocking imported-support issues: 0
- Advisory imported-support issues: 5

### Bundle `b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a63`
- Source version: 1.1.0
- Created at: 2026-04-21T13:00:00Z
- Ready for AOP review: Yes
- Evidence items: 2
- Direct applicability assessments: 1
- Partial applicability assessments: 2
- Indirect applicability assessments: 0
- Non-comparable applicability assessments: 0
- Suggested references: 2
- Attachable Registry artifact refs: 9
- Warning: context_not_assay: Mechanistic context must not be reinterpreted as direct empirical assay evidence for KE or KER support.
- Scientific-review flag: Mechanistic context does not by itself establish KE essentiality or direct KER empirical support.
- Scientific-review flag: study_design_flag: mechanistic_context_not_direct_empirical_proof
- Manual mapping: Manual KE/KER mapping is required before Registry evidence can be attached to draft-specific review claims.
- Manual mapping: Imported AOP-context bundles preserve provenance and caveats, but they do not establish causal directionality or direct empirical sufficiency on their own.

## Recommended Next Actions
- Bring every key event up to the governed review baseline with measurement guidance, applicability metadata, and explicit essentiality status.
- Tighten KE assay routing by enriching key-event titles, structured gene identifiers, and measurement metadata so assay mapping is more specific and complete.
- Fill the missing KER evidence fields explicitly: biological plausibility, empirical support, and quantitative understanding.
- Normalize linked stressors to CAS RN or DTXSID where possible so quantitative ordering review can resolve chemicals deterministically.
- Add explicit KE directionality and KER effect metadata so directional concordance can be reviewed deterministically.

## Limitations and Interpretation
- These results combine draft-graph validation with assay-derived heuristics and should not be treated as a definitive causal proof.
- Quantitative ordering signals are supplemental review evidence, not a curated qAOP model.
- Chemical activity overlays highlight assay-supported draft nodes for one chemical and do not prove full-pathway traversal.
- Use the form 'MIE leading to AO' or 'MIE leading to AO via distinctive KE' where possible.
- Add species / life stage / sex applicability metadata on the draft root.
- Add at least one reference supporting the AOP summary.
- Store a diagram or reference to a graphical AOP representation on the root entity.
- Add corresponding author / point-of-contact metadata for review workflows.
- Link one or more stressors where known; this is especially useful for MIE-centric review.
- 1/2 key events include applicability metadata.
- 0/2 key events include governed essentiality metadata; explicit 'not_assessed' or 'not_reported' counts as coverage.
- 0/1 KERs include empirical support content.
- 0/1 KERs include quantitative understanding content.
- No MIE-to-AO KER steps exposed enough polarity metadata to assess directional concordance. Add KE directionality (for example attributes.direction_of_change) and explicit KER effect metadata (for example attributes.relationship_effect).
- CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived.
- Draft does not currently contain any linked stressors for quantitative review.
- Registry handoff bundles for AOP context preserve supporting evidence, provenance, and bounded-use caveats but do not establish KE or KER truth automatically.
- Imported Registry evidence must remain reviewable support and should not silently replace direct AOP-Wiki, AOP-DB, or empirical assay evidence.
- Chemical trace was not included because no chemical identifier was supplied.
