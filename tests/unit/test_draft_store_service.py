from __future__ import annotations

import pytest

from src.services.draft_store import (
    Draft,
    DraftVersion,
    GraphEntity,
    GraphRelationship,
    GraphSnapshot,
    VersionMetadata,
    InMemoryDraftRepository,
    DraftStoreService,
    CreateDraftInput,
    UpdateDraftInput,
)


def make_entities(label_suffix: str = "1") -> list[GraphEntity]:
    return [
        GraphEntity(
            identifier=f"KE:{label_suffix}",
            type="KeyEvent",
            attributes={"label": f"Event {label_suffix}"},
        )
    ]


def make_relationships(label_suffix: str = "1") -> list[GraphRelationship]:
    return [
        GraphRelationship(
            identifier=f"KER:{label_suffix}",
            source=f"KE:{label_suffix}",
            target=f"KE:{int(label_suffix) + 1}",
            type="KeyEventRelationship",
            attributes={"plausibility": "moderate"},
        )
    ]


def make_service() -> DraftStoreService:
    return DraftStoreService(InMemoryDraftRepository())


def test_create_draft_initializes_version() -> None:
    service = make_service()
    payload = CreateDraftInput(
        draft_id="draft-1",
        title="Example",
        author="alice",
        summary="initial",
        initial_entities=make_entities(),
        initial_relationships=make_relationships(),
    )

    draft = service.create_draft(payload)

    assert draft.draft_id == "draft-1"
    assert len(draft.versions) == 1
    assert draft.versions[0].metadata.author == "alice"


def test_append_version_updates_repository() -> None:
    service = make_service()
    payload = CreateDraftInput(
        draft_id="draft-1",
        title="Example",
        author="alice",
        summary="initial",
        initial_entities=make_entities(),
        initial_relationships=make_relationships(),
    )
    service.create_draft(payload)

    update = UpdateDraftInput(
        draft_id="draft-1",
        version_id="v2",
        author="bob",
        summary="status update",
        entities=[
            GraphEntity(
                identifier="KE:1",
                type="KeyEvent",
                attributes={"label": "Event 1", "status": "review"},
            )
        ],
        relationships=make_relationships(),
        provenance={"source": "unit-test"},
    )

    draft = service.append_version(update)

    assert len(draft.versions) == 2
    assert draft.versions[-1].metadata.summary == "status update"
    assert draft.versions[-1].diff.updated_entities[0].identifier == "KE:1"


def test_append_version_missing_draft_raises() -> None:
    service = make_service()
    update = UpdateDraftInput(
        draft_id="missing",
        version_id="v2",
        author="bob",
        summary="status update",
        entities=make_entities(),
        relationships=make_relationships(),
    )

    with pytest.raises(KeyError):
        service.append_version(update)
