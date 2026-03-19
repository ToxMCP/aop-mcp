from __future__ import annotations

import pytest

from src.server.tools import aop as aop_tools
from src.services.draft_store import (
    DraftStoreService,
    GraphEntity,
    GraphRelationship,
    InMemoryDraftRepository,
    UpdateDraftInput,
)
from src.tools import validate_payload
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
        return {
            "id": aop_id,
            "title": "Example AOP",
            "references": [{"label": "Core AOP reference", "identifier": "10.1000/core-aop", "source": "doi"}],
        }

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
            "references": [{"label": "Assessment reference", "identifier": "PMID:123456", "source": "pmid"}],
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
                "references": [{"label": "KE ref", "identifier": "10.1000/ke-1", "source": "doi"}],
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
                "references": [],
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
                "references": [],
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
                "references": [{"label": "KER ref", "identifier": "10.1000/ker-10", "source": "doi"}],
            },
            "KER:11": {
                "id": "KER:11",
                "title": "Intermediate event leads to adverse outcome",
                "upstream": {"id": "KE:2", "iri": "https://identifiers.org/aop.events/2", "title": "Intermediate event"},
                "downstream": {"id": "KE:3", "iri": "https://identifiers.org/aop.events/3", "title": "Adverse outcome"},
                "biological_plausibility": "Strong support.",
                "empirical_support": "Strong support.",
                "quantitative_understanding": None,
                "references": [],
            },
            "KER:12": {
                "id": "KER:12",
                "title": "MIE leads to adverse outcome",
                "upstream": {"id": "KE:1", "iri": "https://identifiers.org/aop.events/1", "title": "MIE"},
                "downstream": {"id": "KE:3", "iri": "https://identifiers.org/aop.events/3", "title": "Adverse outcome"},
                "biological_plausibility": "Moderate support.",
                "empirical_support": "Moderate support.",
                "quantitative_understanding": "Low support.",
                "references": [],
            },
        }
        return records[ker_id]

    async def get_related_aops(self, aop_id: str, *, limit: int = 20):
        assert aop_id == "AOP:232"
        assert limit == 5
        return [{"id": "AOP:517", "title": "Related", "shared_key_event_count": 3, "shared_ker_count": 1, "total_shared_elements": 4}]


class StubDbAdapter:
    async def list_stressor_chemicals_for_aop(self, aop_id: str):
        assert aop_id == "AOP:232"
        return [
            {
                "stressor_id": "https://identifiers.org/aop.stressor/1",
                "label": "Perfluorooctanesulfonic acid",
                "chemical_iri": "https://identifiers.org/cas/1763-23-1",
                "casrn": "1763-23-1",
            }
        ]


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
async def test_get_aop_tool_returns_oecd_phase1_fields(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    result = await aop_tools.get_aop(
        aop_tools.GetAopInput(aop_id="AOP:232")
    )

    validate_payload(result, namespace="read", name="get_aop.response.schema")
    assert result["id"] == "AOP:232"
    assert result["molecular_initiating_events"][0]["id"] == "KE:1"
    assert result["adverse_outcomes"][0]["id"] == "KE:3"
    assert result["overall_applicability"]["basis"].startswith("Not yet exposed")
    assert result["stressors"][0]["label"] == "Perfluorooctanesulfonic acid"
    assert result["references"][0]["identifier"] == "10.1000/core-aop"
    assert result["references"][1]["identifier"] == "PMID:123456"


@pytest.mark.asyncio
async def test_get_key_event_tool_returns_normalized_oecd_objects(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())

    result = await aop_tools.get_key_event(
        aop_tools.GetKeyEventInput(key_event_id="KE:1")
    )

    validate_payload(result, namespace="read", name="get_key_event.response.schema")
    assert result["event_components"]["action"] is None
    assert result["biological_context"]["organs"][0]["term"]["id"] == "UBERON:0002107"
    assert result["biological_context"]["organs"][0]["evidence_call"] == "moderate"
    assert result["applicability"]["taxa"][0]["term"]["id"] == "NCBITaxon:9606"
    assert result["applicability"]["taxa"][0]["evidence_call"] == "moderate"
    assert result["applicability"]["summary_rationale"] is not None
    assert result["measurement_method_details"][0]["label"] == "Reporter assay"
    assert result["references"][0]["identifier"] == "10.1000/ke-1"


@pytest.mark.asyncio
async def test_get_ker_tool_returns_evidence_blocks(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())

    result = await aop_tools.get_ker(
        aop_tools.GetKerInput(ker_id="KER:10")
    )

    validate_payload(result, namespace="read", name="get_ker.response.schema")
    assert result["evidence_blocks"]["biological_plausibility"]["heuristic_call"] == "strong"
    assert result["evidence_blocks"]["empirical_support"]["heuristic_call"] == "moderate"
    assert result["applicability"]["taxa"][0]["term"]["id"] == "NCBITaxon:9606"
    assert result["applicability"]["life_stages"][0]["term"]["label"] == "adult"
    assert result["applicability"]["sexes"] == []
    assert result["references"][0]["identifier"] == "10.1000/ker-10"


@pytest.mark.asyncio
async def test_get_key_event_infers_action_and_title_object_terms(monkeypatch) -> None:
    class TitleDerivedWikiAdapter:
        async def get_key_event(self, ke_id: str):
            assert ke_id == "KE:239"
            return {
                "id": "KE:239",
                "title": "Activation, Pregnane-X receptor, NR1I2",
                "short_name": "PXR activation",
                "description": "Pregnane X receptor activation event.",
                "measurement_methods": ["Reporter assay"],
                "taxonomic_applicability": ["NCBITaxon:9606"],
                "sex_applicability": None,
                "life_stage_applicability": None,
                "level_of_biological_organization": "molecular",
                "organ_context": [],
                "cell_type_context": [],
                "gene_identifiers": [],
                "protein_identifiers": [],
                "biological_processes": [],
                "part_of_aops": [],
                "references": [],
            }

    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: TitleDerivedWikiAdapter())

    result = await aop_tools.get_key_event(
        aop_tools.GetKeyEventInput(key_event_id="KE:239")
    )

    assert result["event_components"]["action"]["label"] == "activation"
    labels = [item["label"] for item in result["event_components"]["biological_objects"]]
    assert "Pregnane-X receptor" in labels


@pytest.mark.asyncio
async def test_assess_aop_confidence_returns_conservative_heuristic_summary(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())

    result = await aop_tools.assess_aop_confidence(
        aop_tools.AssessAopConfidenceInput(aop_id="AOP:232")
    )

    validate_payload(result, namespace="read", name="assess_aop_confidence.response.schema")
    assert result["aop"]["id"] == "AOP:232"
    assert result["coverage"]["key_event_count"] == 3
    assert result["coverage"]["kers_with_quantitative_understanding"] == 2
    assert result["confidence_dimensions"]["biological_plausibility"]["heuristic_call"] == "strong"
    assert result["confidence_dimensions"]["empirical_support"]["heuristic_call"] == "moderate"
    assert result["confidence_dimensions"]["essentiality_of_key_events"]["heuristic_call"] == "not_assessed"
    assert "overall_aop_evidence" not in result["confidence_dimensions"]
    assert result["supplemental_signals"]["aop_level_evidence_signal"]["heuristic_call"] == "moderate"
    assert result["oecd_alignment"]["status"] == "partial"
    assert result["overall_call"] == "moderate"
    assert result["heuristic_overall_call"] == "moderate"
    assert any("essentiality" in item.lower() for item in result["limitations"])
    assert result["applicability_summary"]["taxonomic_applicability"] == ["NCBITaxon:9606"]
    assert result["overall_applicability"]["taxa"][0]["evidence_call"] == "moderate"
    assert result["overall_applicability"]["summary_rationale"] is not None


@pytest.mark.asyncio
async def test_assess_aop_confidence_derives_bounded_essentiality_heuristic(monkeypatch) -> None:
    class EssentialityWikiAdapter(StubWikiAdapter):
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
            ]

        async def get_aop_assessment(self, aop_id: str):
            record = await super().get_aop_assessment(aop_id)
            record["evidence_summary"] = (
                "Blocking the intermediate event prevented the downstream adverse outcome and "
                "supports key event essentiality."
            )
            return record

    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: EssentialityWikiAdapter())

    result = await aop_tools.assess_aop_confidence(
        aop_tools.AssessAopConfidenceInput(aop_id="AOP:232")
    )

    assert result["confidence_dimensions"]["essentiality_of_key_events"]["heuristic_call"] == "moderate"
    assert result["confidence_dimensions"]["essentiality_of_key_events"]["heuristic_inputs"]["path_count"] == 1
    assert any("heuristically" in item.lower() for item in result["limitations"])


@pytest.mark.asyncio
async def test_assess_aop_confidence_does_not_score_essentiality_from_path_structure_alone(monkeypatch) -> None:
    class StructuralOnlyWikiAdapter(StubWikiAdapter):
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
            ]

        async def get_aop_assessment(self, aop_id: str):
            record = await super().get_aop_assessment(aop_id)
            record["evidence_summary"] = "Overall support is moderate."
            return record

    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StructuralOnlyWikiAdapter())

    result = await aop_tools.assess_aop_confidence(
        aop_tools.AssessAopConfidenceInput(aop_id="AOP:232")
    )

    assert result["confidence_dimensions"]["essentiality_of_key_events"]["heuristic_call"] == "not_assessed"
    assert result["confidence_dimensions"]["essentiality_of_key_events"]["heuristic_inputs"]["path_count"] == 1
    assert "not sufficient" in result["confidence_dimensions"]["essentiality_of_key_events"]["basis"]


def test_extract_essentiality_text_signal_avoids_generic_essential_language() -> None:
    signal, cue_count = aop_tools._extract_essentiality_text_signal(
        [
            "The genes they modulate play essential roles in lipid homeostasis.",
            "GPAT enzymes are necessary for maintaining the balance between lipid storage and fatty acid oxidation.",
            "Lipids are not able to be eliminated as efficiently and can begin to accumulate in the liver.",
            "Opposite directions can cause reduced expression of other isoforms while steatosis is discussed elsewhere in the paragraph.",
        ]
    )

    assert signal == "not_reported"
    assert cue_count == 0


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
            attributes={
                "measurement_methods": ["Reporter assay"],
                "taxonomic_applicability": ["NCBITaxon:9606"],
                "essentiality": {
                    "evidence_call": "moderate",
                    "rationale": "Blocking the event reduced downstream lipid accumulation.",
                    "references": [{"identifier": "PMID:111", "source": "pmid"}],
                },
            },
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
            attributes={
                "measurement": "Histopathology",
                "applicability": {"sex": "female"},
                "essentiality": {
                    "evidence_call": "not_assessed",
                    "rationale": "Direct perturbation evidence has not yet been curated for this draft.",
                    "references": [],
                },
            },
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
    checks = {item["id"]: item for item in result["results"]}
    assert checks["ke_essentiality_shape"]["status"] == "pass"
    assert checks["ke_essentiality_coverage"]["status"] == "pass"


@pytest.mark.asyncio
async def test_validate_draft_oecd_flags_legacy_malformed_essentiality(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-oecd-legacy",
            title="PXR activation leading to liver steatosis",
            description="Initial OECD-style draft.",
            adverse_outcome="Liver steatosis",
            applicability={"species": "human", "life_stage": "adult", "sex": "female"},
            references=[{"title": "Example reference"}],
            author="tester",
            summary="create draft",
        )
    )

    draft_store.append_version(
        UpdateDraftInput(
            draft_id="draft-oecd-legacy",
            version_id="v2",
            author="tester",
            summary="inject legacy malformed ke",
            entities=[
                GraphEntity(
                    identifier="AOP:draft-oecd-legacy",
                    type="AdverseOutcomePathway",
                    attributes={
                        "title": "PXR activation leading to liver steatosis",
                        "description": "Initial OECD-style draft.",
                        "adverse_outcome": "Liver steatosis",
                        "applicability": {"species": "human", "life_stage": "adult", "sex": "female"},
                        "references": [{"title": "Example reference"}],
                    },
                ),
                GraphEntity(
                    identifier="KE:1",
                    type="KeyEvent",
                    attributes={
                        "title": "PXR activation",
                        "measurement_methods": ["Reporter assay"],
                        "essentiality": {
                            "evidence_call": "strong",
                            "rationale": "",
                        },
                    },
                ),
                GraphEntity(
                    identifier="KE:2",
                    type="KeyEvent",
                    attributes={
                        "title": "Liver steatosis",
                        "measurement": "Histopathology",
                    },
                ),
            ],
            relationships=[
                GraphRelationship(
                    identifier="KER:1",
                    source="KE:1",
                    target="KE:2",
                    type="KeyEventRelationship",
                    attributes={"plausibility": "Strong mechanistic rationale"},
                )
            ],
        )
    )

    result = await aop_tools.validate_draft_oecd(
        aop_tools.ValidateDraftOecdInput(draft_id="draft-oecd-legacy")
    )

    checks = {item["id"]: item for item in result["results"]}
    assert checks["ke_essentiality_shape"]["status"] == "fail"
    assert checks["ke_essentiality_shape"]["severity"] == "error"
    assert checks["ke_essentiality_coverage"]["status"] == "fail"
