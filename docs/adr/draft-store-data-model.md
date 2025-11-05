# Draft Store Data Model

## Overview
The draft store captures authoring state for write-path operations. Each draft maintains
an immutable timeline of versions. Every version stores a full graph snapshot covering
AOPs, key events, relationships, and stressor links along with provenance metadata and a
hash-chain friendly checksum.

## Entities
- **GraphEntity** – represents a node within the draft knowledge graph. Includes an
  identifier (CURIE/IRI), type label (e.g., `KeyEvent`), and arbitrary attributes.
- **GraphRelationship** – represents relationships such as KERs or stressor links. Stores
  source/target identifiers, semantic type, and extra attributes.
- **GraphSnapshot** – aggregates all entities and relationships for a version.
- **DraftVersion** – packages a snapshot with version metadata (author, summary, PROV-O
  payload) plus a diff versus the prior version.
- **Draft** – top-level container keyed by `draft_id`. Holds descriptive metadata and an
  ordered collection of versions.

## Provenance & audit
- Each version has a checksum (`sha256`) computed from sorted entity/relationship content.
- `previous_checksum` forms a hash chain across versions to satisfy audit requirements.
- `VersionMetadata.provenance` allows embedding PROV-O statements or external references.

## Diffing strategy
`diff_graphs` performs structural comparisons between two snapshots, returning the set of
added, removed, or updated entities and relationships. Updated entries are detected when
type or attribute dictionaries change.

## Repository contract
`DraftRepository` defines the interface used by service layers. The included
`InMemoryDraftRepository` supports prototyping by storing drafts in-process while enforcing
checksum chaining when new versions are appended. A helper `initialize_version` creates the
seed version (v1) with appropriate diff and checksum defaults.

## Service layer
`DraftStoreService` orchestrates repository operations and exposes higher-level APIs for
`create_draft` and `append_version`. Inputs are expressed as dataclasses ensuring callers
provide author summaries, provenance, and graph payloads. The service automatically computes
diffs between versions and validates existence before appending to maintain a consistent
timeline.

The MCP-facing `WriteTools` layer (under `src/tools/write/`) builds on this service to expose
`create_draft_aop`, `add_or_update_ke`, `add_or_update_ker`, and `link_stressor`. Schema-backed
responses live in `docs/contracts/schemas/write/`, keeping tool contracts compatible with agent
workflows and enabling automated validation in tests.

## Publish planners
`MediaWikiPublishPlanner` and `OWLPublishPlanner` (under `src/services/publish/`) generate
dry-run plans for downstream execution. The MediaWiki planner emits a list of page operations
with Markdown content summaries, while the OWL planner assembles delta dictionaries capturing
individual and relationship updates suitable for AOPOntology ingestion. Both planners operate on
the latest draft version and avoid mutating state, making them safe for preview flows and CI.
