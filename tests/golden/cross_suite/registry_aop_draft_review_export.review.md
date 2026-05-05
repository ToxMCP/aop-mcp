# Draft Review Artifact: Registry-supported mechanistic context review

## Draft Review Summary
- Draft ID: draft-registry-aop-golden
- Version ID: v5
- Adverse outcome: Liver steatosis
- Ready for review: Yes
- Validator errors: 0
- Validator warnings: 12
- Assessable KER quantitative reviews: 0
- Discordant KER quantitative reviews: 0
- Chemical trace included: No

## Validation Findings
- [warning] `title_format`: Use the form 'MIE leading to AO' or 'MIE leading to AO via distinctive KE' where possible.
- [warning] `applicability_present`: Add species / life stage / sex applicability metadata on the draft root.
- [warning] `references_present`: Add at least one reference supporting the AOP summary.
- [warning] `graphical_representation_present`: Store a diagram or reference to a graphical AOP representation on the root entity.
- [warning] `contact_present`: Add corresponding author / point-of-contact metadata for review workflows.
- [warning] `stressor_links`: Link one or more stressors where known; this is especially useful for MIE-centric review.
- [warning] `ke_applicability_coverage`: 1/2 key events include applicability metadata.
- [warning] `ke_essentiality_coverage`: 0/2 key events include governed essentiality metadata; explicit 'not_assessed' or 'not_reported' counts as coverage.
- [warning] `ker_empirical_support_coverage`: 0/1 KERs include empirical support content.
- [warning] `ker_quantitative_support_coverage`: 0/1 KERs include quantitative understanding content.
- [warning] `topology_directional_concordance_assessable`: No MIE-to-AO KER steps exposed enough polarity metadata to assess directional concordance. Add KE directionality (for example attributes.direction_of_change) and explicit KER effect metadata (for example attributes.relationship_effect).
- [warning] `ker_assay_cutoff_ordering_assessable`: CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived.

## Quantitative Review
- Linked stressors: 0
- Searchable stressors: 0
- Assessable relationships: 0
- Concordant relationships: 0
- Discordant relationships: 0

### KER:1 (KE:1 -> KE:2)
- Assay cutoff ordering: not_reported
- Supporting chemicals: 0
- Basis: CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived.

## Chemical Trace
- No chemical trace was requested.

## Evidence Gaps
- Total gaps: 15
- Blocking gaps: 0
- Advisory gaps: 15
- KE assay-mapping gaps: 1

### Global Gaps
- [warning] `title_format`: Use the form 'MIE leading to AO' or 'MIE leading to AO via distinctive KE' where possible.
- [warning] `applicability_present`: Add species / life stage / sex applicability metadata on the draft root.
- [warning] `references_present`: Add at least one reference supporting the AOP summary.
- [warning] `graphical_representation_present`: Store a diagram or reference to a graphical AOP representation on the root entity.
- [warning] `contact_present`: Add corresponding author / point-of-contact metadata for review workflows.
- [warning] `stressor_links`: Link one or more stressors where known; this is especially useful for MIE-centric review.
- [warning] `topology_directional_concordance_assessable`: No MIE-to-AO KER steps exposed enough polarity metadata to assess directional concordance. Add KE directionality (for example attributes.direction_of_change) and explicit KER effect metadata (for example attributes.relationship_effect).
- [warning] `ker_assay_cutoff_ordering_assessable`: CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived.

### Key Event Gaps
- `KE:1` (Activation, Pregnane-X receptor, NR1I2): Key event is missing explicit essentiality metadata
- `KE:2` (Liver steatosis): Key event is missing applicability metadata; Key event is missing explicit essentiality metadata; No candidate assays were found for this key event

### Relationship Gaps
- `KER:1` (KE:1 -> KE:2): KER is missing empirical support evidence; KER is missing quantitative understanding; Assay cutoff ordering is not assessable for this KER

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

## Limitations
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
