from __future__ import annotations

from src.services.draft_store import (
    Draft,
    DraftVersion,
    GraphEntity,
    GraphRelationship,
    GraphSnapshot,
    VersionMetadata,
    diff_graphs,
)
from src.services.publish import MediaWikiPublishPlanner, OWLPublishPlanner


def make_version(version_id: str) -> DraftVersion:
    entities = {
        "AOP:draft-1": GraphEntity(
            identifier="AOP:draft-1",
            type="AdverseOutcomePathway",
            attributes={"title": "Draft AOP", "description": "Example"},
        ),
        "KE:1": GraphEntity(
            identifier="KE:1",
            type="KeyEvent",
            attributes={"title": "Mitochondrial dysfunction"},
        ),
    }
    relationships = {
        "KER:1": GraphRelationship(
            identifier="KER:1",
            source="KE:1",
            target="KE:2",
            type="KeyEventRelationship",
            attributes={"plausibility": "strong"},
        )
    }
    snapshot = GraphSnapshot(entities=entities, relationships=relationships)
    diff = diff_graphs(GraphSnapshot(), snapshot)
    return DraftVersion(
        version_id=version_id,
        graph=snapshot,
        metadata=VersionMetadata(author="alice", summary="Initial"),
        diff=diff,
    )


def test_mediawiki_planner_produces_operations() -> None:
    draft = Draft(draft_id="draft-1", title="Draft AOP", status="draft")
    version = make_version("v2")
    planner = MediaWikiPublishPlanner()
    plan = planner.build_plan(draft, version)
    data = plan.to_dict()
    assert data["target"] == "AOP:draft-1"
    assert data["operations"][0]["dry_run"] is True
    assert "Key Events" in data["operations"][0]["content"]


def test_owl_planner_produces_changes() -> None:
    draft = Draft(draft_id="draft-1", title="Draft AOP", status="draft")
    version = make_version("v2")
    planner = OWLPublishPlanner()
    delta = planner.build_delta(draft, version)
    data = delta.to_dict()
    assert len(data["changes"]) >= 2
    assert data["changes"][0]["action"] == "upsert_individual"
