# OECD-Aligned Target Schema

This document translates the OECD AOP Users' Handbook into concrete MCP payload targets for the read and review surface of the AOP MCP.

It is intended to do three things:
- define the minimum OECD-aligned structure for `AOP`, `KE`, `KER`, and `AOP assessment` responses;
- map the current MCP implementation to that structure;
- identify the next implementation steps before broader integrations such as CAMERA.

This document complements `docs/semantic/ontology-alignment.md`, which focuses on namespace and CURIE policy. The current document is stricter: it defines the response contract we want agents to consume.

## Scope

In scope:
- read-side AOP-Wiki and semantic payloads;
- OECD-aligned assessment structure;
- ontology-backed applicability and event metadata;
- provenance requirements for machine-readable outputs.

Out of scope:
- full CAMERA integration;
- write-path publish automation details;
- creating new ontology terms outside the minimum fields needed for interoperability.

## OECD anchors

The OECD handbook is explicit about the shape of the information that should exist in an AOP description.

| OECD topic | Handbook area | MCP implication |
| --- | --- | --- |
| AOP summary metadata | Section 1, especially KE/KER tables, stressors, network view | `get_aop` should expose more than title/status/abstract. |
| KE modularity | Section 2 | `get_key_event` should represent KEs as reusable standalone units. |
| KE event components | Section 2, "KE Components and Biological Context" | KE outputs should expose structured event components, not only free text. |
| KE measurement | Section 2, "How it is Measured or Detected" | Measurement methods should be structured and clearly separated from pathway confidence. |
| KE biological domain of applicability | Section 2, pages 30-32 | Applicability should include structured terms, evidence calls, and rationale. |
| KER evidence | Section 3 | `get_ker` should expose plausibility, empirical support, quantitative understanding, and applicability as first-class fields. |
| Overall AOP assessment | Section 4, pages 49-55 | `assess_aop_confidence` should derive the overall picture from KER evidence plus KE essentiality. |
| Overall confidence guidance | Annex 1 and Annex 2 | High/moderate/low calls should remain explainable and explicitly partial when data are missing. |

## Design principles

- Keep `KE` and `KER` objects modular. They should remain reusable across AOPs.
- Represent ontology-backed fields explicitly rather than burying them in free text.
- Keep pathway evidence, measurement/method evidence, and regulatory context separate.
- Carry provenance with any derived or normalized field.
- Preserve OECD terminology in output names whenever practical.
- Prefer nullable structured fields over flattening everything into summaries.

## Canonical target objects

### Shared helper objects

#### `OntologyTerm`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `string \| null` | CURIE when known, otherwise `null`. |
| `label` | `string \| null` | Human-readable term label. |
| `source_field` | `string` | Upstream RDF or adapter field that produced the term. |
| `provenance` | `ProvenanceRecord[]` | How the term was obtained or normalized. |

#### `ApplicabilityTerm`

| Field | Type | Notes |
| --- | --- | --- |
| `term` | `OntologyTerm` | Taxon, sex, life-stage, organ, cell type, etc. |
| `evidence_call` | `high \| moderate \| low \| not_reported` | OECD-style applicability evidence call. |
| `rationale` | `string \| null` | Free-text explanation for the applicability selection. |
| `references` | `ReferenceRecord[]` | Optional support references. |
| `provenance` | `ProvenanceRecord[]` | Adapter/source trail. |

#### `MeasurementMethod`

| Field | Type | Notes |
| --- | --- | --- |
| `label` | `string` | Method or assay label. |
| `method_type` | `string \| null` | Assay, guideline, ELISA, transcriptomics, etc. |
| `directness` | `direct \| indirect \| mixed \| unknown` | OECD handbook asks whether the measure is direct or indirect. |
| `fit_for_purpose` | `high \| moderate \| low \| not_reported` | Optional quality annotation. |
| `repeatability` | `high \| moderate \| low \| not_reported` | Optional quality annotation. |
| `reproducibility` | `high \| moderate \| low \| not_reported` | Optional quality annotation. |
| `regulatory_acceptance` | `accepted \| emerging \| research_only \| unknown` | Optional quality annotation. |
| `references` | `ReferenceRecord[]` | Supporting references. |
| `provenance` | `ProvenanceRecord[]` | Source trail. |

#### `EvidenceBlock`

| Field | Type | Notes |
| --- | --- | --- |
| `text` | `string \| null` | Source evidence text. |
| `heuristic_call` | `strong \| moderate \| low \| not_reported \| not_assessed` | Keep derived calls separate from the text itself. |
| `basis` | `string` | How the call was derived. |
| `references` | `ReferenceRecord[]` | Supporting references when available. |
| `provenance` | `ProvenanceRecord[]` | Adapter/source trail. |

#### `ReferenceRecord`

| Field | Type | Notes |
| --- | --- | --- |
| `label` | `string \| null` | Citation label. |
| `identifier` | `string \| null` | DOI, PMID, URL, or internal reference key. |
| `source` | `string \| null` | Upstream reference system. |

#### `ProvenanceRecord`

| Field | Type | Notes |
| --- | --- | --- |
| `source` | `string` | Example: `aop_wiki_rdf`, `derived_from_ke_metadata`. |
| `field` | `string` | Upstream field or query binding. |
| `transformation` | `string \| null` | Normalization, aggregation, heuristic extraction, etc. |
| `confidence` | `high \| moderate \| low \| null` | Confidence in the transformation step. |

### `KE`

| Field | Type | OECD intent |
| --- | --- | --- |
| `id`, `iri`, `title`, `short_name`, `description` | scalar metadata | KE identity and description |
| `event_components.biological_processes` | `OntologyTerm[]` | Structured event component |
| `event_components.biological_objects` | `OntologyTerm[]` | Structured event component |
| `event_components.action` | `OntologyTerm \| null` | Increased/decreased or equivalent action |
| `level_of_biological_organization` | `OntologyTerm \| null` | KE context |
| `biological_context.organs` | `ApplicabilityTerm[]` | Context and applicability |
| `biological_context.cell_types` | `ApplicabilityTerm[]` | Context and applicability |
| `applicability.taxa` | `ApplicabilityTerm[]` | OECD domain of applicability |
| `applicability.life_stages` | `ApplicabilityTerm[]` | OECD domain of applicability |
| `applicability.sexes` | `ApplicabilityTerm[]` | OECD domain of applicability |
| `applicability.summary_rationale` | `string \| null` | Free-text rationale |
| `measurement_methods` | `MeasurementMethod[]` | OECD measurement guidance |
| `mie_specific` | `object \| null` | Only when the KE is an MIE |
| `ao_specific` | `object \| null` | Only when the KE is an AO |
| `part_of_aops` | `AopLink[]` | Network reuse |
| `references` | `ReferenceRecord[]` | Supporting references |
| `provenance` | `ProvenanceRecord[]` | Source and derivation trail |

### `KER`

| Field | Type | OECD intent |
| --- | --- | --- |
| `id`, `iri`, `title`, `description` | scalar metadata | KER identity and narrative |
| `upstream`, `downstream` | `EventLink` | The KER pair |
| `applicability.taxa` | `ApplicabilityTerm[]` | KER biological domain |
| `applicability.life_stages` | `ApplicabilityTerm[]` | KER biological domain |
| `applicability.sexes` | `ApplicabilityTerm[]` | KER biological domain |
| `applicability.summary_rationale` | `string \| null` | Free-text rationale |
| `biological_plausibility` | `EvidenceBlock` | OECD core dimension |
| `empirical_support` | `EvidenceBlock` | OECD core dimension |
| `quantitative_understanding` | `EvidenceBlock` | OECD core dimension |
| `references` | `ReferenceRecord[]` | Supporting references |
| `referenced_aops` | `AopLink[]` | Network reuse |
| `provenance` | `ProvenanceRecord[]` | Source and derivation trail |

### `AOP`

| Field | Type | OECD intent |
| --- | --- | --- |
| `id`, `iri`, `title`, `short_name`, `status`, `abstract` | scalar metadata | Root AOP summary |
| `created`, `modified` | scalar metadata | Versioning context |
| `molecular_initiating_events` | `EventLink[]` | AOP root summary |
| `adverse_outcomes` | `EventLink[]` | AOP root summary |
| `stressors` | `OntologyTerm[]` | Structured stressor links |
| `graph` | `AopGraph \| null` | Graphical/network representation |
| `overall_applicability` | `ApplicabilitySummary` | AOP-level domain of applicability |
| `references` | `ReferenceRecord[]` | Supporting references |
| `provenance` | `ProvenanceRecord[]` | Source and derivation trail |

### `AOP assessment`

| Field | Type | OECD intent |
| --- | --- | --- |
| `overall_applicability` | `ApplicabilitySummary` | Section 4, AOP applicability |
| `essentiality_of_key_events` | `EvidenceBlock` | Section 4, KE essentiality |
| `biological_plausibility` | `EvidenceBlock` | Aggregated from KERs |
| `empirical_support` | `EvidenceBlock` | Aggregated from KERs |
| `quantitative_understanding` | `EvidenceBlock` | Aggregated from KERs |
| `overall_call` | `high \| moderate \| low \| sparse_evidence` | Explainable overall call |
| `rationale` | `string[]` | Short narrative summary |
| `limitations` | `string[]` | Explicit missing pieces |
| `oecd_alignment` | `object` | Whether the result is full, partial, or heuristic |
| `coverage` | `object` | Field-level data availability metrics |
| `provenance` | `ProvenanceRecord[]` | Aggregation and derivation trail |

## Current MCP coverage map

Status legend:
- `complete`: current MCP already exposes the target concept in a usable form.
- `partial`: current MCP exposes related fields, but not yet in the target OECD-aligned structure.
- `missing`: not currently exposed in a first-class way.

### `search_aops` and `get_aop`

| Target area | Current source | Status | Notes |
| --- | --- | --- | --- |
| AOP identity | `get_aop`, `get_aop_assessment` | complete | IDs and titles are present. |
| AOP summary metadata | `get_aop`, `get_aop_assessment` | partial | Status, abstract, created, modified present across two tools, not normalized into one root shape. |
| MIE/AO links | `get_aop_assessment` | partial | Present only in assessment-oriented read path. |
| Stressors | `get_aop` enriched with AOP-DB stressor chemicals | partial | Structured stressor terms are now exposed on the read path, but ontology normalization is still shallow and depends on AOP-DB coverage. |
| Graph/network representation | not exposed | missing | `find_paths_between_events` helps, but root graph is not first-class. |
| Overall applicability | derived in `assess_aop_confidence` | partial | Aggregated from KE metadata, not a dedicated AOP root field. |
| References/provenance | `get_aop`, `get_aop_assessment` plus tool-layer provenance | partial | References are now exposed when the RDF provides them; provenance is present but still tool-layer oriented rather than field-complete. |

### `get_key_event`

| Target area | Current source | Status | Notes |
| --- | --- | --- | --- |
| KE identity and description | `get_key_event` | complete | Core identity, title, short name, description exist. |
| Event components | `biological_processes`, `gene_identifiers`, `protein_identifiers`, `direction_of_change` | partial | Raw pieces exist, but not grouped as `event_components` with ontology semantics. |
| Biological context | `cell_type_context`, `organ_context`, `level_of_biological_organization` | partial | Present, but not normalized into applicability-aware objects. |
| Applicability terms | `taxonomic_applicability`, `sex_applicability`, `life_stage_applicability` | partial | Terms now carry heuristic evidence calls, rationale, references, and provenance, but the upstream RDF still does not expose explicit applicability-strength fields. |
| Measurement methods | `measurement_methods` | partial | Labels only; no directness or quality metadata. |
| MIE/AO-specific content | not exposed | missing | Needed for full OECD shape. |
| References | `get_key_event` | partial | References are now exposed when present in RDF, but coverage is source-dependent and not yet linked to richer citation metadata. |
| Provenance | implicit only | missing | No field-level source trail in payload. |

### `get_ker`

| Target area | Current source | Status | Notes |
| --- | --- | --- | --- |
| KER identity and pair | `get_ker` | complete | Upstream/downstream linkage is present. |
| KER narrative | `description` | complete | Description is exposed. |
| Applicability | derived from shared upstream/downstream KE applicability | partial | KER applicability is now derived conservatively from shared KE applicability terms, but it is still not exposed directly as a first-class upstream RDF field. |
| Biological plausibility | `biological_plausibility` | partial | Text is present, but not structured as a reusable evidence block with references/provenance. |
| Empirical support | `empirical_support` | partial | Same issue as above. |
| Quantitative understanding | `quantitative_understanding` | partial | Same issue as above. |
| References | `get_ker` | partial | References are now exposed when present in RDF, but citation structure is still lightweight. |
| Provenance | implicit only | missing | No field-level source trail in payload. |

### `assess_aop_confidence`

| Target area | Current source | Status | Notes |
| --- | --- | --- | --- |
| OECD core dimensions | `confidence_dimensions` | partial | Correct dimensions are separated, but they are heuristic aggregations over sparse text. |
| Essentiality of KEs | bounded text-plus-path heuristic on `assess_aop_confidence`; governed draft `KE.attributes.essentiality` on the write path | partial | The live read path remains heuristic because the upstream RDF export does not expose a dedicated structured essentiality field. Draft authoring now supports an explicit governed `essentiality` object that can record `evidence_call`, `rationale`, and references for later review. |
| Overall applicability | `applicability_summary` | partial | Derived from KE metadata with structured heuristic evidence calls rather than a dedicated AOP- and KER-level applicability field. |
| Rationales and limitations | `rationale`, `limitations` | complete | Good start, but should eventually reference explicit OECD guiding questions. |
| OECD alignment status | `oecd_alignment` | complete | Correctly warns when the output is only partial. |
| Provenance for derived calls | implicit only | missing | Aggregation logic is in code, not carried as first-class provenance in payloads. |

### `validate_draft_oecd`

| Target area | Current source | Status | Notes |
| --- | --- | --- | --- |
| Root AOP completeness checks | `validate_draft_oecd` | partial | Useful checklist exists, but it does not yet validate ontology-backed fields deeply. |
| KE/KER coverage checks | `validate_draft_oecd` | partial | Presence checks exist, and KE essentiality now has a governed draft contract, but the full target schema is not yet enforced for all draft fields. |
| Applicability presence | `validate_draft_oecd` | partial | Presence only, no structured evidence-call validation. |
| OECD read-model parity | not yet enforced | missing | Draft validation is ahead of the read-model in some places and behind it in others. |

## Ordered implementation sequence

### Phase 1: normalize the read contract

Add reusable response models and apply them first to the read tools:
- `OntologyTerm`
- `ApplicabilityTerm`
- `MeasurementMethod`
- `EvidenceBlock`
- `ReferenceRecord`
- `ProvenanceRecord`

Initial scope:
- `get_key_event`
- `get_ker`
- `get_aop`
- `assess_aop_confidence`

### Phase 2: enrich the AOP-Wiki adapter

Populate the normalized fields from live RDF where possible:
- convert current KE biological process/object/action fragments into explicit `event_components`;
- capture AOP stressor links when available;
- expose references if they are retrievable from the RDF export;
- carry field-level provenance for normalized and aggregated values.

### Phase 3: add applicability evidence structure

Extend KE and KER payloads with:
- applicability terms grouped by taxon, life stage, sex, organ, cell type;
- OECD-style evidence calls per applicability term;
- summary rationale fields for applicability decisions.

### Phase 4: add KE essentiality

This is the highest-value OECD assessment gap.

Implementation target:
- keep the live AOP assessment path conservative until a dedicated upstream essentiality field exists;
- use a governed draft `KE.attributes.essentiality` object to capture explicit essentiality judgments for authoring and review;
- later add evidence type counts such as direct, indirect, contradictory, and no-data;
- eventually expose a resulting `EvidenceBlock` for `essentiality_of_key_events` without relying on loose text inference.

### Phase 5: tighten assessment outputs

Once the underlying fields exist:
- derive overall applicability from KE and KER applicability, not KEs alone;
- point rationales to explicit OECD-style dimensions;
- keep measurement/method evidence out of the core AOP confidence dimensions;
- keep supplemental AOP-level text separate from the OECD core dimensions.

## Non-goal for now: CAMERA integration

The OECD handbook strengthens the case for delaying CAMERA integration until the ontology-backed read contract is stable.

A future CAMERA bridge should consume the normalized objects above, especially:
- `KE.event_components`
- `KE.applicability`
- `KE.measurement_methods`
- `AOP.overall_applicability`
- `AOP assessment.oecd_alignment`

That keeps method evidence and regulatory context interoperable without collapsing them into the AOP evidence model.
