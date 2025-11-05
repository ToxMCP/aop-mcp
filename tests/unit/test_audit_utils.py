from __future__ import annotations

from src.instrumentation.audit import verify_audit_chain
from src.services.draft_store import (
    Draft,
    DraftVersion,
    GraphEntity,
    GraphSnapshot,
    VersionMetadata,
    diff_graphs,
    compute_graph_checksum,
)


def make_draft() -> Draft:
    draft = Draft(draft_id="draft-1", title="Demo", status="draft")
    entity = GraphEntity(identifier="AOP:draft-1", type="AdverseOutcomePathway", attributes={})
    snapshot = GraphSnapshot(entities={entity.identifier: entity}, relationships={})
    version = DraftVersion(
        version_id="v1",
        graph=snapshot,
        metadata=VersionMetadata(author="alice", summary="initial"),
        diff=diff_graphs(GraphSnapshot(), snapshot),
    )
    version.metadata.checksum = compute_graph_checksum(snapshot)
    version.metadata.previous_checksum = None
    draft.add_version(version)
    return draft


def test_verify_audit_chain_returns_true_on_valid_chain() -> None:
    draft = make_draft()
    assert verify_audit_chain(draft) is True


def test_verify_audit_chain_detects_checksum_mismatch() -> None:
    draft = make_draft()
    draft.versions[0].metadata.checksum = "invalid"
    assert verify_audit_chain(draft) is False
