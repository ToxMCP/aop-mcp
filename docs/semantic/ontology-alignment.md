# Ontology Alignment Plan

## Goals
- Align AOP MCP semantic entities with AOPOntology and Biolink Model categories.
- Support CURIE normalization for species, life stage, sex, and stressor identifiers.
- Provide minting strategy for draft IDs while preventing collisions with authoritative CURIE spaces.

## Reference ontologies & namespaces
| Namespace | Prefix | Notes |
|-----------|--------|-------|
| AOPOntology | `aopo` | Primary ontology for AOP entities (AOP, KE, KER). |
| Biolink Model | `biolink` | Provides high-level categories (Pathway, BiologicalProcess). |
| Gene Ontology | `GO` | Needed for mechanistic key events referencing biological processes. |
| Chemical Entities of Biological Interest | `CHEBI` | For stressor chemistry alignment when available. |
| NCBI Taxonomy | `NCBITaxon` | Species applicability normalization. |
| PATO | `PATO` | Sex applicability normalization. |
| HsapDv | `HsapDv` | Human development stages for life stage applicability. |

## CURIE normalization rules
1. Accept input IDs as CURIE or IRI. Convert IRIs to CURIE using known namespace maps.
2. Validate that prefixes appear in an allow-list. Reject unknown prefixes with `SemanticViolation` errors.
3. For draft entities (temporary IDs), mint using prefix `TMP` with UUID suffix, stored separately from authoritative IDs.
4. Maintain lookup tables for common text labels to CURIE (e.g., "human" -> `NCBITaxon:9606`).

## Applicability mapping
- Species: map common names or Latin names via curated table seeded from AOPOntology allowed values.
- Sex: enforce PATO terms (`PATO:0000383` female, `PATO:0000384` male).
- Life stage: align to HsapDv or equivalent ontologies; allow fallback to AOPOntology life stage terms when available.

## Evidence facets
- Biological plausibility: `strong|moderate|weak` enumerations.
- Temporal concordance: `strong|moderate|weak|not assessed`.
- Dose concordance: `strong|moderate|weak|not assessed`.

Store enumerations centrally so MCP tools reuse them, preventing drift.

## Open items
- Confirm availability of AOPOntology SPARQL for term validation or rely on local cached manifests.
- Determine strategy for cross-ontology term updates (e.g., PATO version mismatches).

