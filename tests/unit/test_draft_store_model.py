from __future__ import annotations

from datetime import datetime, timezone

from src.services.draft_store import (
    Draft,
    DraftVersion,
    GraphEntity,
    GraphRelationship,
    GraphSnapshot,
    VersionMetadata,
    diff_graphs,
    compute_graph_checksum,
)


def make_graph(v: int) -> GraphSnapshot:
    node = GraphEntity(identifier=f"KE:{v}", type="KeyEvent", attributes={"label": f"Event {v}"})
    rel = GraphRelationship(
        identifier=f"KER:{v}",
        source=f"KE:{v}",
        target=f"KE:{v+1}",
        type="KeyEventRelationship",
        attributes={"plausibility": "moderate"},
    )
    return GraphSnapshot(entities={node.identifier: node}, relationships={rel.identifier: rel})


def test_diff_graphs_detects_changes() -> None:
    base = make_graph(1)
    updated = make_graph(1)
    updated.entities["KE:1"].attributes = {"label": "Event 1", "status": "draft"}
    updated.relationships["KER:1"].attributes = {"plausibility": "strong"}

    diff = diff_graphs(base, updated)

    assert diff.updated_entities[0].identifier == "KE:1"
    assert diff.updated_relationships[0].identifier == "KER:1"


def test_compute_graph_checksum_changes_with_content() -> None:
    checksum_a = compute_graph_checksum(make_graph(1))
    checksum_b = compute_graph_checksum(make_graph(2))
    assert checksum_a != checksum_b


def test_draft_add_version_updates_timestamp() -> None:
    draft = Draft(draft_id="draft-1", title="Example", status="draft")
    graph = make_graph(1)
    metadata = VersionMetadata(author="alice", summary="initial")
    version = DraftVersion(version_id="v1", graph=graph, metadata=metadata, diff=diff_graphs(GraphSnapshot(), graph))
    draft.add_version(version)
    assert draft.updated_at == metadata.created_at
