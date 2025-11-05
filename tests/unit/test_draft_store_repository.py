from __future__ import annotations

from src.services.draft_store import (
    Draft,
    GraphSnapshot,
    GraphEntity,
    GraphRelationship,
    VersionMetadata,
    DraftVersion,
    diff_graphs,
    InMemoryDraftRepository,
    initialize_version,
)


def make_snapshot() -> GraphSnapshot:
    node = GraphEntity(identifier="KE:1", type="KeyEvent", attributes={"label": "Event"})
    rel = GraphRelationship(
        identifier="KER:1",
        source="KE:1",
        target="KE:2",
        type="KeyEventRelationship",
        attributes={},
    )
    return GraphSnapshot(entities={node.identifier: node}, relationships={rel.identifier: rel})


def test_initialize_version_sets_checksum_and_diff() -> None:
    snapshot = make_snapshot()
    metadata = VersionMetadata(author="alice", summary="initial")
    version = initialize_version("draft-1", "v1", snapshot, metadata)
    assert version.metadata.checksum is not None
    assert version.diff.added_entities[0].identifier == "KE:1"


def test_repository_appends_version_and_updates_audit_chain() -> None:
    repo = InMemoryDraftRepository()
    draft = Draft(draft_id="draft-1", title="Example", status="draft")
    repo.create_draft(draft)

    v1 = initialize_version("draft-1", "v1", make_snapshot(), VersionMetadata(author="alice", summary="initial"))
    repo.append_version("draft-1", v1)

    # second version with updated attributes
    snapshot_v2 = make_snapshot()
    snapshot_v2.entities["KE:1"].attributes = {"label": "Event", "status": "review"}
    v2 = DraftVersion(
        version_id="v2",
        graph=snapshot_v2,
        metadata=VersionMetadata(author="bob", summary="status update"),
        diff=diff_graphs(v1.graph, snapshot_v2),
    )
    repo.append_version("draft-1", v2)

    stored = repo.get_draft("draft-1")
    assert stored is not None
    assert len(stored.versions) == 2
    assert stored.versions[-1].metadata.previous_checksum == stored.versions[0].metadata.checksum
