from __future__ import annotations

import pytest

from src.services.draft_store import DraftStoreService, InMemoryDraftRepository
from src.tools import validate_payload
from src.tools.write import (
    DraftApplicability,
    KeyEventPayload,
    KeyEventRelationshipPayload,
    StressorLinkPayload,
    WriteTools,
)


def make_tools() -> WriteTools:
    repository = InMemoryDraftRepository()
    service = DraftStoreService(repository)
    return WriteTools(service)


def test_create_draft_aop_returns_schema_compliant_payload() -> None:
    tools = make_tools()
    response = tools.create_draft_aop(
        draft_id="draft-1",
        title="Draft AOP",
        description="Example",
        adverse_outcome="AO:1",
        applicability=DraftApplicability(species="NCBITaxon:9606", life_stage="HsapDv:0000087", sex="PATO:0000383"),
        references=[{"title": "Ref"}],
        author="alice",
        summary="Initial draft",
        tags=["demo"],
    )
    validate_payload(response, namespace="write", name="create_draft_aop.response.schema")
    assert response == {"draft_id": "draft-1", "version_id": "v1"}


def test_add_or_update_ke_updates_graph() -> None:
    repository = InMemoryDraftRepository()
    service = DraftStoreService(repository)
    tools = WriteTools(service)
    tools.create_draft_aop(
        draft_id="draft-1",
        title="Draft AOP",
        description="Example",
        adverse_outcome="AO:1",
        applicability=None,
        references=None,
        author="alice",
        summary="Initial draft",
    )
    response = tools.add_or_update_ke(
        draft_id="draft-1",
        version_id="v2",
        author="bob",
        summary="Add KE",
        payload=KeyEventPayload(identifier="KE:1", title="Mitochondrial dysfunction", event_type="Cellular"),
    )
    validate_payload(response, namespace="write", name="update_draft.response.schema")
    assert response == {"draft_id": "draft-1", "version_id": "v2"}
    draft = service.get_draft("draft-1")
    assert draft is not None
    assert draft.versions[-1].graph.entities["KE:1"].attributes["title"] == "Mitochondrial dysfunction"


def test_add_or_update_ke_normalizes_governed_essentiality_payload() -> None:
    repository = InMemoryDraftRepository()
    service = DraftStoreService(repository)
    tools = WriteTools(service)
    tools.create_draft_aop(
        draft_id="draft-1",
        title="Draft AOP",
        description="Example",
        adverse_outcome="AO:1",
        applicability=None,
        references=None,
        author="alice",
        summary="Initial draft",
    )

    tools.add_or_update_ke(
        draft_id="draft-1",
        version_id="v2",
        author="bob",
        summary="Add KE",
        payload=KeyEventPayload(
            identifier="KE:1",
            title="Intermediate event",
            event_type="Cellular",
            attributes={
                "essentiality": {
                    "evidence_call": "moderate",
                    "rationale": "Blocking the event reduced the downstream outcome.",
                    "references": [{"identifier": "PMID:123456", "source": "pmid"}],
                }
            },
        ),
    )

    draft = service.get_draft("draft-1")
    assert draft is not None
    essentiality = draft.versions[-1].graph.entities["KE:1"].attributes["essentiality"]
    assert essentiality["evidence_call"] == "moderate"
    assert essentiality["rationale"] == "Blocking the event reduced the downstream outcome."
    assert essentiality["references"][0]["identifier"] == "PMID:123456"
    assert essentiality["provenance"] == []


@pytest.mark.parametrize(
    ("essentiality", "expected_message"),
    [
        (
            {"evidence_call": "strong", "rationale": "Bad vocabulary."},
            "evidence_call",
        ),
        (
            {"evidence_call": "moderate", "rationale": " ", "references": []},
            "rationale",
        ),
    ],
)
def test_add_or_update_ke_rejects_malformed_essentiality_payload(
    essentiality: dict[str, object],
    expected_message: str,
) -> None:
    tools = make_tools()
    tools.create_draft_aop(
        draft_id="draft-1",
        title="Draft AOP",
        description="Example",
        adverse_outcome="AO:1",
        applicability=None,
        references=None,
        author="alice",
        summary="Initial draft",
    )

    with pytest.raises(ValueError, match=expected_message):
        tools.add_or_update_ke(
            draft_id="draft-1",
            version_id="v2",
            author="bob",
            summary="Add KE",
            payload=KeyEventPayload(
                identifier="KE:1",
                title="Intermediate event",
                attributes={"essentiality": essentiality},
            ),
        )


def test_add_or_update_ker_requires_existing_key_events() -> None:
    tools = make_tools()
    tools.create_draft_aop(
        draft_id="draft-1",
        title="Draft AOP",
        description="Example",
        adverse_outcome="AO:1",
        applicability=None,
        references=None,
        author="alice",
        summary="Initial draft",
    )
    tools.add_or_update_ke(
        draft_id="draft-1",
        version_id="v2",
        author="bob",
        summary="Add KE1",
        payload=KeyEventPayload(identifier="KE:1", title="KE1", event_type=None),
    )
    tools.add_or_update_ke(
        draft_id="draft-1",
        version_id="v3",
        author="bob",
        summary="Add KE2",
        payload=KeyEventPayload(identifier="KE:2", title="KE2", event_type=None),
    )
    response = tools.add_or_update_ker(
        draft_id="draft-1",
        version_id="v4",
        author="bob",
        summary="Link KER",
        payload=KeyEventRelationshipPayload(
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
            plausibility="strong",
            status="review",
        ),
    )
    validate_payload(response, namespace="write", name="update_draft.response.schema")
    assert response == {"draft_id": "draft-1", "version_id": "v4"}


def test_link_stressor_creates_entity_and_relationship() -> None:
    tools = make_tools()
    tools.create_draft_aop(
        draft_id="draft-1",
        title="Draft AOP",
        description="Example",
        adverse_outcome="AO:1",
        applicability=None,
        references=None,
        author="alice",
        summary="Initial draft",
    )
    tools.add_or_update_ke(
        draft_id="draft-1",
        version_id="v2",
        author="bob",
        summary="Add KE",
        payload=KeyEventPayload(identifier="KE:1", title="KE1", event_type=None),
    )
    response = tools.link_stressor(
        draft_id="draft-1",
        version_id="v3",
        author="bob",
        summary="Link stressor",
        payload=StressorLinkPayload(
            stressor_id="CHEBI:1",
            label="Chemical X",
            source="CompTox",
            target="KE:1",
            provenance={"reference": "CompTox"},
        ),
    )
    validate_payload(response, namespace="write", name="update_draft.response.schema")
    assert response == {"draft_id": "draft-1", "version_id": "v3"}


def test_add_or_update_ker_raises_when_missing_key_event() -> None:
    tools = make_tools()
    tools.create_draft_aop(
        draft_id="draft-1",
        title="Draft AOP",
        description="Example",
        adverse_outcome="AO:1",
        applicability=None,
        references=None,
        author="alice",
        summary="Initial draft",
    )
    with pytest.raises(ValueError):
        tools.add_or_update_ker(
            draft_id="draft-1",
            version_id="v2",
            author="bob",
            summary="Invalid KER",
            payload=KeyEventRelationshipPayload(
                identifier="KER:1",
                upstream="KE:1",
                downstream="KE:2",
            ),
        )
