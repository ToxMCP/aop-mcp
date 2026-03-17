from __future__ import annotations

import pytest

from src.server.tools import aop as aop_tools
from src.services.draft_store import DraftStoreService, InMemoryDraftRepository
from src.tools.write import WriteTools


class StubWikiAdapter:
    async def list_key_events(self, aop_id: str):
        assert aop_id == "AOP:232"
        return [
            {"id": "KE:1", "title": "MIE"},
            {"id": "KE:2", "title": "Intermediate event"},
            {"id": "KE:3", "title": "Adverse outcome"},
        ]

    async def list_kers(self, aop_id: str):
        assert aop_id == "AOP:232"
        return [
            {
                "id": "KER:10",
                "upstream": {"id": "KE:1", "iri": "https://identifiers.org/aop.events/1"},
                "downstream": {"id": "KE:2", "iri": "https://identifiers.org/aop.events/2"},
            },
            {
                "id": "KER:11",
                "upstream": {"id": "KE:2", "iri": "https://identifiers.org/aop.events/2"},
                "downstream": {"id": "KE:3", "iri": "https://identifiers.org/aop.events/3"},
            },
            {
                "id": "KER:12",
                "upstream": {"id": "KE:1", "iri": "https://identifiers.org/aop.events/1"},
                "downstream": {"id": "KE:3", "iri": "https://identifiers.org/aop.events/3"},
            },
        ]

    async def get_aop(self, aop_id: str):
        return {"id": aop_id, "title": "Example AOP"}

    async def get_aop_assessment(self, aop_id: str):
        assert aop_id == "AOP:232"
        return {
            "id": aop_id,
            "title": "Example AOP",
            "abstract": "Example abstract",
            "evidence_summary": "Overall Moderate support.",
            "molecular_initiating_events": [
                {"id": "KE:1", "iri": "https://identifiers.org/aop.events/1", "title": "MIE"}
            ],
            "adverse_outcomes": [
                {"id": "KE:3", "iri": "https://identifiers.org/aop.events/3", "title": "Adverse outcome"}
            ],
        }

    async def get_key_event(self, ke_id: str):
        records = {
            "KE:1": {
                "id": "KE:1",
                "title": "MIE",
                "measurement_methods": ["Reporter assay"],
                "taxonomic_applicability": ["NCBITaxon:9606"],
                "sex_applicability": "female",
                "life_stage_applicability": "adult",
                "level_of_biological_organization": "molecular",
                "organ_context": ["UBERON:0002107"],
                "cell_type_context": [],
            },
            "KE:2": {
                "id": "KE:2",
                "title": "Intermediate event",
                "measurement_methods": ["Transcriptomics"],
                "taxonomic_applicability": ["NCBITaxon:9606"],
                "sex_applicability": None,
                "life_stage_applicability": "adult",
                "level_of_biological_organization": "cellular",
                "organ_context": ["UBERON:0002107"],
                "cell_type_context": ["CL:0000182"],
            },
            "KE:3": {
                "id": "KE:3",
                "title": "Adverse outcome",
                "measurement_methods": [],
                "taxonomic_applicability": [],
                "sex_applicability": None,
                "life_stage_applicability": None,
                "level_of_biological_organization": "organ",
                "organ_context": ["UBERON:0002107"],
                "cell_type_context": [],
            },
        }
        return records[ke_id]

    async def get_ker(self, ker_id: str):
        records = {
            "KER:10": {
                "id": "KER:10",
                "title": "MIE leads to intermediate event",
                "upstream": {"id": "KE:1", "iri": "https://identifiers.org/aop.events/1", "title": "MIE"},
                "downstream": {"id": "KE:2", "iri": "https://identifiers.org/aop.events/2", "title": "Intermediate event"},
                "biological_plausibility": "Strong mechanistic rationale.",
                "empirical_support": "Moderate support from dose-response studies.",
                "quantitative_understanding": "Moderate quantitative support.",
            },
            "KER:11": {
                "id": "KER:11",
                "title": "Intermediate event leads to adverse outcome",
                "upstream": {"id": "KE:2", "iri": "https://identifiers.org/aop.events/2", "title": "Intermediate event"},
                "downstream": {"id": "KE:3", "iri": "https://identifiers.org/aop.events/3", "title": "Adverse outcome"},
                "biological_plausibility": "Strong support.",
                "empirical_support": "Strong support.",
                "quantitative_understanding": None,
            },
            "KER:12": {
                "id": "KER:12",
                "title": "MIE leads to adverse outcome",
                "upstream": {"id": "KE:1", "iri": "https://identifiers.org/aop.events/1", "title": "MIE"},
                "downstream": {"id": "KE:3", "iri": "https://identifiers.org/aop.events/3", "title": "Adverse outcome"},
                "biological_plausibility": "Moderate support.",
                "empirical_support": "Moderate support.",
                "quantitative_understanding": "Low support.",
            },
        }
        return records[ker_id]

    async def get_related_aops(self, aop_id: str, *, limit: int = 20):
        assert aop_id == "AOP:232"
        assert limit == 5
        return [{"id": "AOP:517", "title": "Related", "shared_key_event_count": 3, "shared_ker_count": 1, "total_shared_elements": 4}]


@pytest.mark.asyncio
async def test_find_paths_between_events_returns_multiple_paths(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())

    result = await aop_tools.find_paths_between_events(
        aop_tools.FindPathsBetweenEventsInput(
            aop_id="AOP:232",
            source_event_id="KE:1",
            target_event_id="KE:3",
            max_depth=3,
            limit=5,
        )
    )

    assert result["path_count"] == 2
    assert result["results"][0]["event_path"][0]["id"] == "KE:1"
    assert result["results"][0]["event_path"][-1]["id"] == "KE:3"


@pytest.mark.asyncio
async def test_get_related_aops_tool_wraps_source_aop(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())

    result = await aop_tools.get_related_aops(
        aop_tools.GetRelatedAopsInput(
            aop_id="AOP:232",
            limit=5,
        )
    )

    assert result["aop"]["id"] == "AOP:232"
    assert result["results"][0]["id"] == "AOP:517"


@pytest.mark.asyncio
async def test_assess_aop_confidence_returns_conservative_heuristic_summary(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())

    result = await aop_tools.assess_aop_confidence(
        aop_tools.AssessAopConfidenceInput(aop_id="AOP:232")
    )

    assert result["aop"]["id"] == "AOP:232"
    assert result["coverage"]["key_event_count"] == 3
    assert result["coverage"]["kers_with_quantitative_understanding"] == 2
    assert result["confidence_dimensions"]["biological_plausibility"]["heuristic_call"] == "strong"
    assert result["confidence_dimensions"]["empirical_support"]["heuristic_call"] == "moderate"
    assert result["confidence_dimensions"]["essentiality_of_key_events"]["heuristic_call"] == "not_assessed"
    assert result["heuristic_overall_call"] == "moderate"
    assert any("essentiality" in item.lower() for item in result["limitations"])
    assert result["applicability_summary"]["taxonomic_applicability"] == ["NCBITaxon:9606"]


@pytest.mark.asyncio
async def test_validate_draft_oecd_reports_readiness_and_warnings(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-oecd",
            title="PXR activation leading to liver steatosis",
            description="Initial OECD-style draft.",
            adverse_outcome="Liver steatosis",
            applicability={"species": "human", "life_stage": "adult", "sex": "female"},
            references=[{"title": "Example reference"}],
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-oecd",
            version_id="v2",
            author="tester",
            summary="add ke1",
            identifier="KE:1",
            title="PXR activation",
            attributes={"measurement_methods": ["Reporter assay"], "taxonomic_applicability": ["NCBITaxon:9606"]},
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-oecd",
            version_id="v3",
            author="tester",
            summary="add ke2",
            identifier="KE:2",
            title="Liver steatosis",
            attributes={"measurement": "Histopathology", "applicability": {"sex": "female"}},
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-oecd",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
            plausibility="Strong mechanistic rationale",
            attributes={
                "empirical_support": "Dose and temporal concordance observed.",
                "quantitative_understanding": "Moderate quantitative support.",
            },
        )
    )
    await aop_tools.link_stressor(
        aop_tools.StressorLinkInputModel(
            draft_id="draft-oecd",
            version_id="v5",
            author="tester",
            summary="link stressor",
            stressor_id="CHEM:1",
            label="PFOS",
            source="manual",
            target="KE:1",
        )
    )

    result = await aop_tools.validate_draft_oecd(
        aop_tools.ValidateDraftOecdInput(draft_id="draft-oecd")
    )

    assert result["draft_id"] == "draft-oecd"
    assert result["version_id"] == "v5"
    assert result["summary"]["error_count"] == 0
    assert result["summary"]["ready_for_review"] is True
    assert result["summary"]["warning_count"] >= 1
