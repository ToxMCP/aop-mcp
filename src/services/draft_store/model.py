"""Data model for draft AOP write-path workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Dict, Iterable, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class GraphEntity:
    """Represents a node in the draft knowledge graph."""

    identifier: str
    type: str
    attributes: Mapping[str, object]


@dataclass
class GraphRelationship:
    """Represents an edge (e.g., KER, stressor link) in the draft graph."""

    identifier: str
    source: str
    target: str
    type: str
    attributes: Mapping[str, object]


@dataclass
class GraphSnapshot:
    """Immutable snapshot of draft graph state for a given version."""

    entities: Dict[str, GraphEntity] = field(default_factory=dict)
    relationships: Dict[str, GraphRelationship] = field(default_factory=dict)


@dataclass
class DraftDiff:
    """Difference between two graph snapshots."""

    added_entities: list[GraphEntity] = field(default_factory=list)
    removed_entities: list[GraphEntity] = field(default_factory=list)
    updated_entities: list[GraphEntity] = field(default_factory=list)
    added_relationships: list[GraphRelationship] = field(default_factory=list)
    removed_relationships: list[GraphRelationship] = field(default_factory=list)
    updated_relationships: list[GraphRelationship] = field(default_factory=list)


@dataclass
class VersionMetadata:
    """Provenance and audit information for a draft version."""

    author: str
    summary: str
    created_at: datetime = field(default_factory=_utcnow)
    provenance: Mapping[str, object] = field(default_factory=dict)
    checksum: str | None = None
    previous_checksum: str | None = None


@dataclass
class DraftVersion:
    """Represents a single revision of a draft."""

    version_id: str
    graph: GraphSnapshot
    metadata: VersionMetadata
    diff: DraftDiff


@dataclass
class Draft:
    """Aggregates draft metadata and revision timeline."""

    draft_id: str
    title: str
    status: str
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    versions: list[DraftVersion] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def add_version(self, version: DraftVersion) -> None:
        self.versions.append(version)
        self.updated_at = version.metadata.created_at


def diff_graphs(base: GraphSnapshot, updated: GraphSnapshot) -> DraftDiff:
    diff = DraftDiff()

    base_entities = base.entities
    updated_entities = updated.entities

    for identifier, entity in updated_entities.items():
        if identifier not in base_entities:
            diff.added_entities.append(entity)
        else:
            base_entity = base_entities[identifier]
            if (
                entity.type != base_entity.type
                or dict(entity.attributes) != dict(base_entity.attributes)
            ):
                diff.updated_entities.append(entity)

    for identifier, entity in base_entities.items():
        if identifier not in updated_entities:
            diff.removed_entities.append(entity)

    base_rels = base.relationships
    updated_rels = updated.relationships

    for identifier, rel in updated_rels.items():
        if identifier not in base_rels:
            diff.added_relationships.append(rel)
        else:
            base_rel = base_rels[identifier]
            if (
                rel.type != base_rel.type
                or rel.source != base_rel.source
                or rel.target != base_rel.target
                or dict(rel.attributes) != dict(base_rel.attributes)
            ):
                diff.updated_relationships.append(rel)

    for identifier, rel in base_rels.items():
        if identifier not in updated_rels:
            diff.removed_relationships.append(rel)

    return diff


def compute_graph_checksum(graph: GraphSnapshot) -> str:
    """Produces a deterministic checksum for audit chaining."""

    hasher = sha256()

    for identifier in sorted(graph.entities):
        entity = graph.entities[identifier]
        hasher.update(identifier.encode("utf-8"))
        hasher.update(entity.type.encode("utf-8"))
        for key in sorted(entity.attributes):
            hasher.update(key.encode("utf-8"))
            hasher.update(repr(entity.attributes[key]).encode("utf-8"))

    for identifier in sorted(graph.relationships):
        rel = graph.relationships[identifier]
        hasher.update(identifier.encode("utf-8"))
        hasher.update(rel.type.encode("utf-8"))
        hasher.update(rel.source.encode("utf-8"))
        hasher.update(rel.target.encode("utf-8"))
        for key in sorted(rel.attributes):
            hasher.update(key.encode("utf-8"))
            hasher.update(repr(rel.attributes[key]).encode("utf-8"))

    return hasher.hexdigest()


def snapshot_from_iterables(
    entities: Iterable[GraphEntity],
    relationships: Iterable[GraphRelationship],
) -> GraphSnapshot:
    return GraphSnapshot(
        entities={entity.identifier: entity for entity in entities},
        relationships={rel.identifier: rel for rel in relationships},
    )

