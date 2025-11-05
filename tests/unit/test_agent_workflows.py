from __future__ import annotations

from dataclasses import asdict

from src.agent.workflows import WorkflowFactory
from src.services.draft_store import (
    Draft,
    DraftVersion,
    GraphEntity,
    GraphSnapshot,
    VersionMetadata,
    diff_graphs,
)
from src.services.jobs import JobRecord, JobService
from src.tools.semantic import SemanticTools, SemanticToolConfig
from src.tools.write import WriteTools
from src.services.draft_store import DraftStoreService, InMemoryDraftRepository


def make_draft_version() -> tuple[Draft, DraftVersion]:
    draft = Draft(draft_id="draft-1", title="Demo", status="draft")
    entity = GraphEntity(identifier="AOP:draft-1", type="AdverseOutcomePathway", attributes={"description": "Example"})
    snapshot = GraphSnapshot(entities={entity.identifier: entity}, relationships={})
    version = DraftVersion(
        version_id="v1",
        graph=snapshot,
        metadata=VersionMetadata(author="alice", summary="initial"),
        diff=diff_graphs(GraphSnapshot(), snapshot),
    )
    return draft, version


def make_factory() -> WorkflowFactory:
    # minimal tool setup
    semantic = SemanticTools(
        config=SemanticToolConfig(
            curie_namespaces={"NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_"},
            species_map={"human": "NCBITaxon:9606"},
            life_stage_map={},
            sex_map={},
        )
    )
    write = WriteTools(DraftStoreService(InMemoryDraftRepository()))
    jobs = JobService()
    return WorkflowFactory(semantic_tools=semantic, write_tools=write, job_service=jobs)


def test_publish_workflow_generates_plan() -> None:
    factory = make_factory()
    workflow = factory.build_publish_workflow()
    draft, version = make_draft_version()
    job = JobRecord(job_id="job-1", type="publish")
    state = workflow.run(draft=draft, version=version, job=job)
    assert "plan" in state
    assert "mediawiki" in state["plan"]
    assert state["enqueue"] == "job-1"

