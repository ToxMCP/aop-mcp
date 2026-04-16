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
    version.metadata.previous_checksum = ""
    version.metadata.checksum_algorithm = "sha256-v1"
    draft.add_version(version)
    return draft


def test_verify_audit_chain_returns_true_on_valid_chain() -> None:
    draft = make_draft()
    assert verify_audit_chain(draft) is True


def test_verify_audit_chain_detects_checksum_mismatch() -> None:
    draft = make_draft()
    draft.versions[0].metadata.checksum = "invalid"
    assert verify_audit_chain(draft) is False


def test_verify_audit_chain_detects_algorithm_mismatch() -> None:
    draft = make_draft()
    draft.versions[0].metadata.checksum_algorithm = "md5-v1"
    assert verify_audit_chain(draft) is False


def test_verify_audit_chain_detects_broken_chain() -> None:
    draft = make_draft()
    # Add a second version with a wrong previous_checksum
    snapshot = GraphSnapshot(entities={}, relationships={})
    checksum = compute_graph_checksum(snapshot)
    version = DraftVersion(
        version_id="v2",
        graph=snapshot,
        metadata=VersionMetadata(author="bob", summary="update"),
        diff=diff_graphs(make_draft().versions[0].graph, snapshot),
    )
    version.metadata.checksum = checksum
    version.metadata.previous_checksum = "wrong-previous"
    version.metadata.checksum_algorithm = "sha256-v1"
    draft.add_version(version)
    assert verify_audit_chain(draft) is False


def test_verify_audit_chain_validates_multi_version_chain() -> None:
    draft = make_draft()
    first_checksum = draft.versions[0].metadata.checksum

    snapshot = GraphSnapshot(entities={}, relationships={})
    checksum = compute_graph_checksum(snapshot)
    version = DraftVersion(
        version_id="v2",
        graph=snapshot,
        metadata=VersionMetadata(author="bob", summary="update"),
        diff=diff_graphs(draft.versions[0].graph, snapshot),
    )
    version.metadata.checksum = checksum
    version.metadata.previous_checksum = first_checksum
    version.metadata.checksum_algorithm = "sha256-v1"
    draft.add_version(version)
    assert verify_audit_chain(draft) is True


def test_version_metadata_add_signature() -> None:
    from src.services.draft_store import ElectronicSignature

    metadata = VersionMetadata(author="alice", summary="initial")
    sig = ElectronicSignature(
        signer_user_id="alice",
        signature_meaning="authored",
        timestamp_utc="2026-01-01T00:00:00Z",
        content_hash="abc123",
        signature_value="base64sig",
    )
    metadata.add_signature(sig)
    assert len(metadata.signatures) == 1
    assert metadata.signatures[0].signature_meaning == "authored"
