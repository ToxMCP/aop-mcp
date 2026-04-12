from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.server.tools import aop as aop_tools
from src.services.draft_store import DraftStoreService, InMemoryDraftRepository
from src.tools.write import WriteTools


class StubWikiAdapter:
    async def search_aops(self, *, text: str | None = None, limit: int = 25):
        assert text == "liver steatosis"
        assert limit == 8
        return [
            {"id": "AOP:529", "title": "PPAR steatosis"},
            {"id": "AOP:591", "title": "DBDPE NAFLD"},
            {"id": "AOP:57", "title": "AhR steatosis"},
        ]

    async def get_key_event(self, ke_id: str):
        assert ke_id == "KE:239"
        return {
            "id": "KE:239",
            "title": "Activation, Pregnane-X receptor, NR1I2",
            "short_name": "PXR activation",
            "description": "Pregnane X receptor activation event.",
        }


class StubDbAdapter:
    single_aop_results = [
        {
            "aeid": 2309,
            "assay_name": "CCTE_GLTED_hDIO1",
            "assay_component_endpoint_name": "CCTE_GLTED_hDIO1",
            "assay_component_endpoint_desc": "DIO1 activity assay",
            "assay_function_type": "enzymatic activity",
            "target_family": "deiodinase",
            "target_family_sub": "deiodinase Type 1",
            "gene_symbols": ["DIO1"],
            "support_count": 1,
            "max_hitcall": 0.98,
            "supporting_chemicals": [
                {
                    "preferred_name": "Perfluorooctanesulfonic acid",
                    "dtxsid": "DTXSID3031864",
                    "casrn": "1763-23-1",
                    "stressor_id": "https://identifiers.org/aop.stressor/771",
                    "stressor_label": "PFOS",
                    "hitcall": 0.98,
                    "activity_cutoff": 20.0,
                }
            ],
        }
    ]
    single_aop_diagnostics = {
        "aop_id": "AOP:529",
        "comptox_api_key_configured": True,
        "stressor_count": 1,
        "chemical_match_count": 1,
        "bioactivity_hit_count": 1,
        "returned_assay_count": 1,
        "empty_reason": None,
        "warnings": [],
    }

    async def search_assays_for_key_event(
        self,
        key_event: dict[str, object],
        *,
        limit: int = 25,
    ):
        assert key_event["id"] == "KE:239"
        assert limit == 3
        return {
            "derived_search_terms": {
                "gene_symbols": ["NR1I2", "PXR"],
                "phrases": ["pregnane x receptor"],
            },
            "limitations": [
                "Assays are ranked by key-event-derived gene and phrase matches in the CompTox assay catalog; this is not a curated KE-to-assay ontology mapping."
            ],
            "results": [
                {
                    "aeid": 103,
                    "assay_name": "ATG_PXRE_CIS",
                    "gene_symbols": ["NR1I2"],
                    "match_score": 245,
                    "match_basis": ["gene_symbol_exact"],
                    "matched_terms": ["NR1I2"],
                    "source": "comptox_assay_catalog",
                }
            ],
        }

    async def list_assays_for_aop_with_diagnostics(
        self,
        aop_id: str,
        *,
        limit: int = 25,
        min_hitcall: float = 0.9,
    ):
        assert aop_id == "AOP:529"
        assert limit == 5
        assert min_hitcall == 0.95
        return {
            "results": self.single_aop_results,
            "diagnostics": self.single_aop_diagnostics,
        }

    async def list_assays_for_aops(
        self,
        aop_ids: list[str],
        *,
        limit: int = 25,
        per_aop_limit: int = 15,
        min_hitcall: float = 0.9,
    ):
        assert aop_ids == ["AOP:529", "AOP:591"]
        assert limit == 5
        assert per_aop_limit == 4
        assert min_hitcall == 0.95
        return [
            {
                "aeid": 2309,
                "assay_name": "CCTE_GLTED_hDIO1",
                "assay_component_endpoint_name": "CCTE_GLTED_hDIO1",
                "assay_component_endpoint_desc": "DIO1 activity assay",
                "assay_function_type": "enzymatic activity",
                "target_family": "deiodinase",
                "target_family_sub": "deiodinase Type 1",
                "gene_symbols": ["DIO1"],
                "aop_support_count": 2,
                "supporting_aops": ["AOP:529", "AOP:591"],
                "chemical_support_count": 2,
                "supporting_chemicals": [
                    {
                        "preferred_name": "Perfluorooctanesulfonic acid",
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "max_hitcall": 1.0,
                        "best_activity_cutoff": 20.0,
                        "aop_ids": ["AOP:529", "AOP:591"],
                        "stressor_ids": ["https://identifiers.org/aop.stressor/771"],
                        "stressor_labels": ["PFOS"],
                    },
                    {
                        "preferred_name": "DBDPE",
                        "dtxsid": "DTXSID9999999",
                        "casrn": "84852-53-9",
                        "max_hitcall": 0.95,
                        "best_activity_cutoff": 25.0,
                        "aop_ids": ["AOP:529", "AOP:591"],
                        "stressor_ids": ["https://identifiers.org/aop.stressor/999"],
                        "stressor_labels": ["DBDPE"],
                    },
                ],
                "max_hitcall": 1.0,
                "chemical_support_count": 2,
            }
        ]

    async def list_assays_for_aops_with_diagnostics(
        self,
        aop_ids: list[str],
        *,
        limit: int = 25,
        per_aop_limit: int = 15,
        min_hitcall: float = 0.9,
    ):
        results = await self.list_assays_for_aops(
            aop_ids,
            limit=limit,
            per_aop_limit=per_aop_limit,
            min_hitcall=min_hitcall,
        )
        return {
            "results": results,
            "diagnostics": {
                "requested_aop_ids": ["AOP:529", "AOP:591"],
                "processed_aop_ids": ["AOP:529", "AOP:591"],
                "returned_assay_count": 1,
                "per_aop": [
                    self.single_aop_diagnostics,
                    {
                        "aop_id": "AOP:591",
                        "comptox_api_key_configured": True,
                        "stressor_count": 1,
                        "chemical_match_count": 1,
                        "bioactivity_hit_count": 1,
                        "returned_assay_count": 1,
                        "empty_reason": None,
                        "warnings": [],
                    },
                ],
                "warnings": [],
            },
        }

    async def discover_orphan_stressors_for_aop_with_diagnostics(
        self,
        aop_id: str,
        *,
        assay_limit: int = 10,
        per_assay_chemical_limit: int = 25,
        limit: int = 25,
        min_hitcall: float = 0.9,
    ):
        assert aop_id == "AOP:529"
        assert assay_limit == 3
        assert per_assay_chemical_limit == 12
        assert limit == 4
        assert min_hitcall == 0.95
        return {
            "results": [
                {
                    "dtxsid": "DTXSID0000001",
                    "casrn": "111-11-1",
                    "preferred_name": "Alpha candidate",
                    "supporting_assay_count": 2,
                    "best_assay_rank": 1,
                    "max_specificity_score": 0.8,
                    "supporting_assays": [
                        {
                            "aeid": 103,
                            "assay_name": "ATG_PXRE_CIS",
                            "rank": 1,
                            "specificity_score": 0.8,
                        },
                        {
                            "aeid": 104,
                            "assay_name": "ATG_PXRE_CONFIRM",
                            "rank": 2,
                            "specificity_score": 0.6,
                        },
                    ],
                }
            ],
            "diagnostics": {
                "aop_id": "AOP:529",
                "comptox_api_key_configured": True,
                "curated_stressor_count": 1,
                "curated_chemical_match_count": 1,
                "assay_candidate_count": 2,
                "scanned_assay_count": 2,
                "assay_chemical_hit_count": 5,
                "returned_candidate_count": 1,
                "empty_reason": None,
                "warnings": [],
            },
        }

    async def discover_orphan_stressors_for_aops_with_diagnostics(
        self,
        aop_ids: list[str],
        *,
        limit: int = 25,
        per_aop_limit: int = 10,
        per_assay_chemical_limit: int = 25,
        min_hitcall: float = 0.9,
    ):
        assert aop_ids == ["AOP:529", "AOP:591"]
        assert limit == 4
        assert per_aop_limit == 3
        assert per_assay_chemical_limit == 12
        assert min_hitcall == 0.95
        return {
            "results": [
                {
                    "dtxsid": "DTXSID0000001",
                    "casrn": "111-11-1",
                    "preferred_name": "Alpha candidate",
                    "aop_support_count": 2,
                    "supporting_aops": ["AOP:529", "AOP:591"],
                    "supporting_assay_count": 3,
                    "best_assay_rank": 1,
                    "max_specificity_score": 0.8,
                    "supporting_assays": [
                        {
                            "aop_id": "AOP:529",
                            "aeid": 103,
                            "assay_name": "ATG_PXRE_CIS",
                            "rank": 1,
                            "specificity_score": 0.8,
                        },
                        {
                            "aop_id": "AOP:591",
                            "aeid": 103,
                            "assay_name": "ATG_PXRE_CIS",
                            "rank": 1,
                            "specificity_score": 0.8,
                        },
                        {
                            "aop_id": "AOP:529",
                            "aeid": 104,
                            "assay_name": "ATG_PXRE_CONFIRM",
                            "rank": 2,
                            "specificity_score": 0.6,
                        },
                    ],
                }
            ],
            "diagnostics": {
                "requested_aop_ids": ["AOP:529", "AOP:591"],
                "processed_aop_ids": ["AOP:529", "AOP:591"],
                "returned_candidate_count": 1,
                "per_aop": [
                    {
                        "aop_id": "AOP:529",
                        "comptox_api_key_configured": True,
                        "curated_stressor_count": 1,
                        "curated_chemical_match_count": 1,
                        "assay_candidate_count": 2,
                        "scanned_assay_count": 2,
                        "assay_chemical_hit_count": 5,
                        "returned_candidate_count": 1,
                        "empty_reason": None,
                        "warnings": [],
                    },
                    {
                        "aop_id": "AOP:591",
                        "comptox_api_key_configured": True,
                        "curated_stressor_count": 1,
                        "curated_chemical_match_count": 1,
                        "assay_candidate_count": 2,
                        "scanned_assay_count": 2,
                        "assay_chemical_hit_count": 4,
                        "returned_candidate_count": 1,
                        "empty_reason": None,
                        "warnings": [],
                    },
                ],
                "warnings": [],
            },
        }


class StubTraceDbAdapter:
    async def search_assays_for_key_event(
        self,
        key_event: dict[str, object],
        *,
        limit: int = 25,
    ):
        assert limit in {3, 5}
        if key_event["id"] == "KE:1":
            return {
                "derived_search_terms": {
                    "gene_symbols": ["NR1I2", "PXR"],
                    "phrases": ["pregnane x receptor"],
                },
                "limitations": [],
                "results": [
                    {
                        "aeid": 101,
                        "assay_name": "ATG_PXRE_CIS",
                        "match_score": 245,
                        "rank_score": 260.0,
                        "specificity_score": 0.75,
                        "match_basis": ["gene_symbol_exact"],
                        "matched_terms": ["NR1I2"],
                        "source": "comptox_assay_catalog",
                        "gene_symbols": ["NR1I2"],
                    }
                ],
            }
        if key_event["id"] == "KE:2":
            return {
                "derived_search_terms": {
                    "gene_symbols": [],
                    "phrases": ["steatosis"],
                },
                "limitations": [
                    "This key event did not expose gene-like symbols, so assay matching relies on phrase similarity and may be broader."
                ],
                "results": [
                    {
                        "aeid": 202,
                        "assay_name": "HTS_STEATOSIS_PANEL",
                        "match_score": 180,
                        "rank_score": 189.0,
                        "specificity_score": 0.45,
                        "match_basis": ["phrase_exact"],
                        "matched_terms": ["steatosis"],
                        "source": "comptox_assay_catalog",
                        "gene_symbols": [],
                    }
                ],
            }
        raise AssertionError(f"Unexpected key event id: {key_event['id']}")


class StubTraceCompTox:
    has_api_key = True

    def search_equal(self, value: str):
        assert value == "DTXSID3031864"
        return [
            {
                "dtxsid": "DTXSID3031864",
                "preferredName": "Perfluorooctanesulfonic acid",
                "casrn": "1763-23-1",
                "inchikey": "ABCDEF",
            }
        ]

    def bioactivity_data_by_dtxsid(self, dtxsid: str):
        assert dtxsid == "DTXSID3031864"
        return [
            {"aeid": 101, "hitc": 0.97, "coff": 12.0},
            {"aeid": 202, "hitc": 0.40, "coff": 28.0},
            {"aeid": 999, "hitc": 0.95, "coff": 7.0},
        ]


class StubDraftOrderingCompTox:
    has_api_key = True

    def search_equal(self, value: str):
        assert value in {"1763-23-1", "Perfluorooctanesulfonic acid"}
        return [
            {
                "dtxsid": "DTXSID3031864",
                "preferredName": "Perfluorooctanesulfonic acid",
                "casrn": "1763-23-1",
            }
        ]

    def bioactivity_data_by_dtxsid(self, dtxsid: str):
        assert dtxsid == "DTXSID3031864"
        return [
            {"aeid": 101, "hitc": 0.97, "coff": 12.0},
            {"aeid": 202, "hitc": 0.95, "coff": 28.0},
        ]


class StubDraftOrderingDbAdapter(StubTraceDbAdapter):
    def __init__(self) -> None:
        self.comptox = StubDraftOrderingCompTox()


class StubDraftBundleCompTox:
    has_api_key = True

    def search_equal(self, value: str):
        assert value in {"DTXSID3031864", "1763-23-1", "Perfluorooctanesulfonic acid"}
        return [
            {
                "dtxsid": "DTXSID3031864",
                "preferredName": "Perfluorooctanesulfonic acid",
                "casrn": "1763-23-1",
                "inchikey": "ABCDEF",
            }
        ]

    def bioactivity_data_by_dtxsid(self, dtxsid: str):
        assert dtxsid == "DTXSID3031864"
        return [
            {"aeid": 101, "hitc": 0.97, "coff": 12.0},
            {"aeid": 202, "hitc": 0.95, "coff": 28.0},
            {"aeid": 999, "hitc": 0.50, "coff": 7.0},
        ]


class StubDraftBundleDbAdapter(StubTraceDbAdapter):
    def __init__(self) -> None:
        self.comptox = StubDraftBundleCompTox()


class StubDraftEvidenceGapCompTox:
    has_api_key = True

    def search_equal(self, value: str):
        assert value in {"PFOS", "Perfluorooctanesulfonic acid"}
        return [
            {
                "dtxsid": "DTXSID3031864",
                "preferredName": "Perfluorooctanesulfonic acid",
                "casrn": "1763-23-1",
            }
        ]

    def bioactivity_data_by_dtxsid(self, dtxsid: str):
        assert dtxsid == "DTXSID3031864"
        return [
            {"aeid": 101, "hitc": 0.97, "coff": 12.0},
        ]


class StubDraftEvidenceGapDbAdapter:
    def __init__(self) -> None:
        self.comptox = StubDraftEvidenceGapCompTox()

    async def search_assays_for_key_event(
        self,
        key_event: dict[str, object],
        *,
        limit: int = 25,
    ):
        assert limit in {3, 5}
        if key_event["id"] == "KE:1":
            return {
                "derived_search_terms": {
                    "gene_symbols": ["NR1I2", "PXR"],
                    "phrases": ["pregnane x receptor"],
                },
                "limitations": [],
                "results": [
                    {
                        "aeid": 101,
                        "assay_name": "ATG_PXRE_CIS",
                        "match_score": 245,
                        "rank_score": 260.0,
                        "specificity_score": 0.75,
                        "match_basis": ["gene_symbol_exact"],
                        "matched_terms": ["NR1I2"],
                        "source": "comptox_assay_catalog",
                        "gene_symbols": ["NR1I2"],
                    }
                ],
            }
        if key_event["id"] == "KE:2":
            return {
                "derived_search_terms": {
                    "gene_symbols": [],
                    "phrases": ["steatosis"],
                },
                "limitations": [
                    "This key event did not expose gene-like symbols, so assay matching relies on phrase similarity and may be broader.",
                    "No CompTox assay candidates matched the derived key-event terms.",
                ],
                "results": [],
            }
        raise AssertionError(f"Unexpected key event id: {key_event['id']}")


@pytest.mark.asyncio
async def test_search_assays_for_key_event_returns_ke_context(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    result = await aop_tools.search_assays_for_key_event(
        aop_tools.SearchAssaysForKeyEventInput(
            key_event_id="KE:239",
            limit=3,
        )
    )

    assert result["key_event"]["id"] == "KE:239"
    assert result["derived_search_terms"]["gene_symbols"] == ["NR1I2", "PXR"]
    assert result["results"][0]["aeid"] == 103


def test_search_assays_for_key_event_input_accepts_legacy_alias() -> None:
    params = aop_tools.SearchAssaysForKeyEventInput(
        ke_id="KE:239",
        limit=3,
    )

    assert params.key_event_id == "KE:239"


@pytest.mark.asyncio
async def test_list_assays_for_query_resolves_search_then_aggregates(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    result = await aop_tools.list_assays_for_query(
        aop_tools.ListAssaysForQueryInput(
            query="liver steatosis",
            search_limit=8,
            aop_limit=2,
            limit=5,
            per_aop_limit=4,
            min_hitcall=0.95,
        )
    )

    assert [row["id"] for row in result["selected_aops"]] == ["AOP:529", "AOP:591"]
    assert result["results"][0]["aeid"] == 2309
    assert result["results"][0]["aop_support_count"] == 2
    assert result["diagnostics"] == {
        "query": "liver steatosis",
        "matched_aop_count": 3,
        "selected_aop_count": 2,
        "returned_assay_count": 1,
        "per_aop": [
            {
                "aop_id": "AOP:529",
                "comptox_api_key_configured": True,
                "stressor_count": 1,
                "chemical_match_count": 1,
                "bioactivity_hit_count": 1,
                "returned_assay_count": 1,
                "empty_reason": None,
                "warnings": [],
            },
            {
                "aop_id": "AOP:591",
                "comptox_api_key_configured": True,
                "stressor_count": 1,
                "chemical_match_count": 1,
                "bioactivity_hit_count": 1,
                "returned_assay_count": 1,
                "empty_reason": None,
                "warnings": [],
            },
        ],
        "warnings": [
            "Selected the top 2 AOP matches from 3 query results."
        ],
    }


@pytest.mark.asyncio
async def test_discover_orphan_stressors_for_query_resolves_search_then_aggregates(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    result = await aop_tools.discover_orphan_stressors_for_query(
        aop_tools.DiscoverOrphanStressorsForQueryInput(
            query="liver steatosis",
            search_limit=8,
            aop_limit=2,
            limit=4,
            per_aop_limit=3,
            per_assay_chemical_limit=12,
            min_hitcall=0.95,
        )
    )

    assert [row["id"] for row in result["selected_aops"]] == ["AOP:529", "AOP:591"]
    assert result["results"][0]["preferred_name"] == "Alpha candidate"
    assert result["results"][0]["aop_support_count"] == 2
    assert result["diagnostics"] == {
        "query": "liver steatosis",
        "matched_aop_count": 3,
        "selected_aop_count": 2,
        "returned_candidate_count": 1,
        "per_aop": [
            {
                "aop_id": "AOP:529",
                "comptox_api_key_configured": True,
                "curated_stressor_count": 1,
                "curated_chemical_match_count": 1,
                "assay_candidate_count": 2,
                "scanned_assay_count": 2,
                "assay_chemical_hit_count": 5,
                "returned_candidate_count": 1,
                "empty_reason": None,
                "warnings": [],
            },
            {
                "aop_id": "AOP:591",
                "comptox_api_key_configured": True,
                "curated_stressor_count": 1,
                "curated_chemical_match_count": 1,
                "assay_candidate_count": 2,
                "scanned_assay_count": 2,
                "assay_chemical_hit_count": 4,
                "returned_candidate_count": 1,
                "empty_reason": None,
                "warnings": [],
            },
        ],
        "warnings": [
            "Selected the top 2 AOP matches from 3 query results."
        ],
    }


@pytest.mark.asyncio
async def test_get_assays_for_aop_alias_matches_list_assays_for_aop(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    list_result = await aop_tools.list_assays_for_aop(
        aop_tools.ListAssaysForAopInput(
            aop_id="AOP:529",
            limit=5,
            min_hitcall=0.95,
        )
    )
    alias_result = await aop_tools.get_assays_for_aop(
        aop_tools.GetAssaysForAopInput(
            aop_id="AOP:529",
            limit=5,
            min_hitcall=0.95,
        )
    )

    assert alias_result == list_result


@pytest.mark.asyncio
async def test_discover_orphan_stressors_for_aop_returns_ranked_candidates(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    result = await aop_tools.discover_orphan_stressors_for_aop(
        aop_tools.DiscoverOrphanStressorsForAopInput(
            aop_id="AOP:529",
            assay_limit=3,
            per_assay_chemical_limit=12,
            limit=4,
            min_hitcall=0.95,
        )
    )

    assert result["results"][0]["preferred_name"] == "Alpha candidate"
    assert result["results"][0]["supporting_assay_count"] == 2
    assert result["results"][0]["supporting_assays"][0]["aeid"] == 103
    assert result["diagnostics"]["returned_candidate_count"] == 1


@pytest.mark.asyncio
async def test_discover_orphan_stressors_for_aops_returns_cross_pathway_candidates(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    result = await aop_tools.discover_orphan_stressors_for_aops(
        aop_tools.DiscoverOrphanStressorsForAopsInput(
            aop_ids=["AOP:529", "AOP:591"],
            limit=4,
            per_aop_limit=3,
            per_assay_chemical_limit=12,
            min_hitcall=0.95,
        )
    )

    assert result["results"][0]["preferred_name"] == "Alpha candidate"
    assert result["results"][0]["aop_support_count"] == 2
    assert result["results"][0]["supporting_assays"][0]["aop_id"] == "AOP:529"
    assert result["diagnostics"]["returned_candidate_count"] == 1


@pytest.mark.asyncio
async def test_get_assays_for_aops_alias_matches_list_assays_for_aops(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    list_result = await aop_tools.list_assays_for_aops(
        aop_tools.ListAssaysForAopsInput(
            aop_ids=["AOP:529", "AOP:591"],
            limit=5,
            per_aop_limit=4,
            min_hitcall=0.95,
        )
    )
    alias_result = await aop_tools.get_assays_for_aops(
        aop_tools.GetAssaysForAopsInput(
            aop_ids=["AOP:529", "AOP:591"],
            limit=5,
            per_aop_limit=4,
            min_hitcall=0.95,
        )
    )

    assert alias_result == list_result


@pytest.mark.asyncio
async def test_export_assays_table_supports_query_and_csv(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_wiki_adapter", lambda: StubWikiAdapter())
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    result = await aop_tools.export_assays_table(
        aop_tools.ExportAssaysTableInput(
            query="liver steatosis",
            format="csv",
            search_limit=8,
            aop_limit=2,
            limit=5,
            per_aop_limit=4,
            min_hitcall=0.95,
        )
    )

    assert result["filename"] == "assays_liver_steatosis.csv"
    assert result["row_count"] == 1
    assert "aeid,assay_name" in result["content"]
    assert "CCTE_GLTED_hDIO1" in result["content"]
    assert "AOP:529|AOP:591" in result["content"]


@pytest.mark.asyncio
async def test_export_assays_table_supports_explicit_aops_and_tsv(monkeypatch) -> None:
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDbAdapter())

    result = await aop_tools.export_assays_table(
        aop_tools.ExportAssaysTableInput(
            aop_ids=["AOP:529", "AOP:591"],
            format="tsv",
            limit=5,
            per_aop_limit=4,
            min_hitcall=0.95,
        )
    )

    assert result["filename"] == "assays_2_aops.tsv"
    assert result["row_count"] == 1
    assert "aeid\tassay_name" in result["content"]


@pytest.mark.asyncio
async def test_trace_chemical_on_draft_projects_activity_onto_key_events(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubTraceDbAdapter())
    monkeypatch.setattr(aop_tools, "get_comptox_client", lambda: StubTraceCompTox())

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-trace",
            title="PXR activation leading to liver steatosis",
            description="Draft for chemical tracing.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-trace",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
            attributes={
                "measurement_methods": ["Reporter assay"],
                "taxonomic_applicability": ["NCBITaxon:9606"],
            },
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-trace",
            version_id="v3",
            author="tester",
            summary="add ao",
            identifier="KE:2",
            title="Liver steatosis",
            event_role="ao",
            attributes={
                "measurement": "Histopathology",
            },
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-trace",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
            plausibility="Strong mechanistic rationale.",
        )
    )

    result = await aop_tools.trace_chemical_on_draft(
        aop_tools.TraceChemicalOnDraftInput(
            draft_id="draft-trace",
            dtxsid="DTXSID3031864",
            assay_limit=3,
            min_hitcall=0.9,
        )
    )

    assert result["draft_id"] == "draft-trace"
    assert result["version_id"] == "v4"
    assert result["chemical"]["preferred_name"] == "Perfluorooctanesulfonic acid"
    assert result["summary"]["key_event_count"] == 2
    assert result["summary"]["active_key_event_count"] == 1
    assert result["summary"]["inactive_key_event_count"] == 1
    assert result["summary"]["chemical_bioactivity_assay_count"] == 3
    assert [item["id"] for item in result["key_events"]] == ["KE:1", "KE:2"]
    assert result["key_events"][0]["activity_state"] == "active"
    assert result["key_events"][0]["max_hitcall"] == 0.97
    assert result["key_events"][0]["top_assays"][0]["active"] is True
    assert result["key_events"][1]["activity_state"] == "inactive"
    assert result["key_events"][1]["top_assays"][0]["hitcall"] == 0.4
    assert result["relationships"] == [
        {
            "id": "KER:1",
            "source": "KE:1",
            "target": "KE:2",
            "type": "KeyEventRelationship",
            "plausibility": "Strong mechanistic rationale.",
            "status": None,
        }
    ]


@pytest.mark.asyncio
async def test_review_draft_assay_cutoff_ordering_returns_per_ker_quantitative_details(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftOrderingDbAdapter())

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-ordering-review",
            title="PXR activation leading to liver steatosis",
            description="Draft for assay-cutoff ordering review.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-ordering-review",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
            attributes={
                "measurement_methods": ["Reporter assay"],
                "taxonomic_applicability": ["NCBITaxon:9606"],
            },
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-ordering-review",
            version_id="v3",
            author="tester",
            summary="add ao",
            identifier="KE:2",
            title="Liver steatosis",
            event_role="ao",
            attributes={"measurement": "Histopathology"},
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-ordering-review",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
            plausibility="Strong mechanistic rationale.",
        )
    )
    await aop_tools.link_stressor(
        aop_tools.StressorLinkInputModel(
            draft_id="draft-ordering-review",
            version_id="v5",
            author="tester",
            summary="link stressor",
            stressor_id="CHEM:PFOS",
            label="Perfluorooctanesulfonic acid",
            source="1763-23-1",
            target="KE:1",
        )
    )

    result = await aop_tools.review_draft_assay_cutoff_ordering(
        aop_tools.ReviewDraftAssayCutoffOrderingInput(
            draft_id="draft-ordering-review",
            assay_limit=3,
            stressor_limit=5,
            min_hitcall=0.9,
        )
    )

    assert result["draft_id"] == "draft-ordering-review"
    assert result["version_id"] == "v5"
    assert result["review_parameters"] == {
        "assay_limit": 3,
        "stressor_limit": 5,
        "min_hitcall": 0.9,
    }
    assert result["summary"] == {
        "key_event_count": 2,
        "relationship_count": 1,
        "linked_stressor_count": 1,
        "scanned_stressor_count": 1,
        "searchable_stressor_count": 1,
        "assessable_relationship_count": 1,
        "concordant_relationship_count": 1,
        "discordant_relationship_count": 0,
        "not_reported_relationship_count": 0,
        "supporting_chemical_count": 1,
    }
    assert result["stressors"] == [
        {
            "stressor_id": "CHEM:PFOS",
            "label": "Perfluorooctanesulfonic acid",
            "source": "1763-23-1",
            "casrn": "1763-23-1",
            "dtxsid": None,
            "linked_target_ids": ["KE:1"],
            "searchable": True,
        }
    ]
    assert [item["id"] for item in result["key_events"]] == ["KE:1", "KE:2"]
    assert result["relationships"][0]["assay_cutoff_ordering_call"] == "moderate"
    assert result["relationships"][0]["assay_cutoff_supporting_chemical_count"] == 1
    assert result["relationships"][0]["assay_cutoff_ordering"]["supporting_chemicals"][0] == {
        "dtxsid": "DTXSID3031864",
        "preferred_name": "Perfluorooctanesulfonic acid",
        "casrn": "1763-23-1",
        "upstream_best_activity_cutoff": 12.0,
        "downstream_best_activity_cutoff": 28.0,
        "ordering": "concordant",
    }
    assert result["limitations"] == []


@pytest.mark.asyncio
async def test_review_draft_bundle_aggregates_validation_quantitative_review_and_trace(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())
    monkeypatch.setattr(aop_tools, "get_comptox_client", lambda: StubDraftBundleCompTox())

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-review-bundle",
            title="PXR activation leading to liver steatosis",
            description="Draft bundle review example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-review-bundle",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
            attributes={
                "measurement_methods": ["Reporter assay"],
                "taxonomic_applicability": ["NCBITaxon:9606"],
            },
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-review-bundle",
            version_id="v3",
            author="tester",
            summary="add ao",
            identifier="KE:2",
            title="Liver steatosis",
            event_role="ao",
            attributes={"measurement": "Histopathology"},
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-review-bundle",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
            plausibility="Strong mechanistic rationale.",
        )
    )
    await aop_tools.link_stressor(
        aop_tools.StressorLinkInputModel(
            draft_id="draft-review-bundle",
            version_id="v5",
            author="tester",
            summary="link stressor",
            stressor_id="CHEM:PFOS",
            label="Perfluorooctanesulfonic acid",
            source="1763-23-1",
            target="KE:1",
        )
    )

    result = await aop_tools.review_draft_bundle(
        aop_tools.ReviewDraftBundleInput(
            draft_id="draft-review-bundle",
            dtxsid="DTXSID3031864",
            assay_limit=3,
            stressor_limit=5,
            min_hitcall=0.9,
        )
    )

    assert result["draft_id"] == "draft-review-bundle"
    assert result["version_id"] == "v5"
    assert result["review_parameters"] == {
        "assay_limit": 3,
        "stressor_limit": 5,
        "min_hitcall": 0.9,
        "chemical_trace_requested": True,
    }
    assert result["chemical_query"] == {
        "dtxsid": "DTXSID3031864",
        "cas": None,
        "inchikey": None,
        "name": None,
    }
    assert result["bundle_summary"]["ready_for_review"] is True
    assert result["bundle_summary"]["assay_cutoff_assessable_relationship_count"] == 1
    assert result["bundle_summary"]["assay_cutoff_discordant_relationship_count"] == 0
    assert result["bundle_summary"]["chemical_trace_included"] is True
    assert result["bundle_summary"]["traced_key_event_count"] == 2
    assert result["bundle_summary"]["active_key_event_count"] == 2
    assert result["bundle_summary"]["total_gap_count"] >= 1
    assert result["bundle_summary"]["blocking_gap_count"] >= 0
    assert result["bundle_summary"]["advisory_gap_count"] >= 1
    assert result["evidence_gap_summary"]["total_gap_count"] >= 1
    assert result["evidence_gaps"]["summary"] == result["evidence_gap_summary"]
    assert result["evidence_gaps"]["bundle_summary"]["ready_for_review"] is True
    assert result["evidence_gaps"]["key_events"]
    assert result["validation"]["draft_id"] == "draft-review-bundle"
    assert result["quantitative_review"]["relationships"][0]["assay_cutoff_ordering_call"] == "moderate"
    assert result["chemical_trace"]["chemical"]["preferred_name"] == "Perfluorooctanesulfonic acid"
    assert result["chemical_trace"]["summary"]["active_key_event_count"] == 2
    assert result["limitations"]


@pytest.mark.asyncio
async def test_review_draft_evidence_gaps_returns_actionable_gap_report(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftEvidenceGapDbAdapter())

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-evidence-gaps",
            title="PXR activation leading to liver steatosis",
            description="Draft evidence-gap example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-evidence-gaps",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
            attributes={
                "measurement_methods": ["Reporter assay"],
                "taxonomic_applicability": ["NCBITaxon:9606"],
            },
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-evidence-gaps",
            version_id="v3",
            author="tester",
            summary="add downstream ke",
            identifier="KE:2",
            title="Liver steatosis",
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-evidence-gaps",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
        )
    )
    await aop_tools.link_stressor(
        aop_tools.StressorLinkInputModel(
            draft_id="draft-evidence-gaps",
            version_id="v5",
            author="tester",
            summary="link stressor",
            stressor_id="CHEM:PFOS",
            label="PFOS",
            source="PFOS",
            target="KE:1",
        )
    )

    result = await aop_tools.review_draft_evidence_gaps(
        aop_tools.ReviewDraftEvidenceGapsInput(
            draft_id="draft-evidence-gaps",
            assay_limit=3,
            stressor_limit=5,
            min_hitcall=0.9,
        )
    )

    assert result["draft_id"] == "draft-evidence-gaps"
    assert result["version_id"] == "v5"
    assert result["review_parameters"] == {
        "assay_limit": 3,
        "stressor_limit": 5,
        "min_hitcall": 0.9,
    }
    assert result["summary"]["ready_for_review"] is True
    assert result["summary"]["assay_mapping_gap_count"] == 1
    assert result["summary"]["total_gap_count"] >= 8
    assert any(gap["id"] == "applicability_present" for gap in result["global_gaps"])
    assert any(gap["id"] == "references_present" for gap in result["global_gaps"])

    key_events = {item["id"]: item for item in result["key_events"]}
    assert {gap["id"] for gap in key_events["KE:1"]["gaps"]} == {"missing_essentiality"}
    assert {
        gap["id"] for gap in key_events["KE:2"]["gaps"]
    } == {
        "missing_event_role",
        "missing_measurement_guidance",
        "missing_applicability_metadata",
        "missing_essentiality",
        "no_assay_candidates",
    }

    relationship = result["relationships"][0]
    assert relationship["assay_cutoff_ordering_call"] == "not_reported"
    assert {
        gap["id"] for gap in relationship["gaps"]
    } == {
        "missing_plausibility",
        "missing_empirical_support",
        "missing_quantitative_understanding",
        "assay_cutoff_not_assessable",
    }

    stressor = result["stressors"][0]
    assert stressor["label"] == "PFOS"
    assert stressor["searchable"] is True
    assert {gap["id"] for gap in stressor["gaps"]} == {"missing_structured_identifier"}
    assert any("assign explicit `event_role` values" in item for item in result["recommendations"])
    assert any("Normalize linked stressors" in item for item in result["recommendations"])


@pytest.mark.asyncio
async def test_export_draft_review_artifact_renders_markdown(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())
    monkeypatch.setattr(aop_tools, "get_comptox_client", lambda: StubDraftBundleCompTox())

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-export",
            title="PXR activation leading to liver steatosis",
            description="Draft export example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-export",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
            attributes={"measurement_methods": ["Reporter assay"]},
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-export",
            version_id="v3",
            author="tester",
            summary="add ao",
            identifier="KE:2",
            title="Liver steatosis",
            event_role="ao",
            attributes={"measurement": "Histopathology"},
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-export",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
            plausibility="Strong mechanistic rationale.",
        )
    )
    await aop_tools.link_stressor(
        aop_tools.StressorLinkInputModel(
            draft_id="draft-export",
            version_id="v5",
            author="tester",
            summary="link stressor",
            stressor_id="CHEM:PFOS",
            label="Perfluorooctanesulfonic acid",
            source="1763-23-1",
            target="KE:1",
        )
    )

    result = await aop_tools.export_draft_review_artifact(
        aop_tools.ExportDraftReviewArtifactInput(
            draft_id="draft-export",
            format="markdown",
            dtxsid="DTXSID3031864",
            assay_limit=3,
            stressor_limit=5,
            min_hitcall=0.9,
        )
    )

    assert result["format"] == "markdown"
    assert result["artifact_profile"] == "review"
    assert result["filename"] == "draft_review_draft_export.md"
    assert result["bundle_summary"]["chemical_trace_included"] is True
    assert result["evidence_gap_summary"]["total_gap_count"] >= 1
    assert "Draft Review Artifact" in result["content"]
    assert "## Validation Findings" in result["content"]
    assert "## Quantitative Review" in result["content"]
    assert "## Chemical Trace" in result["content"]
    assert "## Evidence Gaps" in result["content"]
    assert "## Recommended Next Actions" in result["content"]


@pytest.mark.asyncio
async def test_export_draft_review_artifact_supports_publication_markdown(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())
    monkeypatch.setattr(aop_tools, "get_comptox_client", lambda: StubDraftBundleCompTox())

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-export-publication",
            title="PXR activation leading to liver steatosis",
            description="Draft export example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-export-publication",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
            attributes={"measurement_methods": ["Reporter assay"]},
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-export-publication",
            version_id="v3",
            author="tester",
            summary="add ao",
            identifier="KE:2",
            title="Liver steatosis",
            event_role="ao",
            attributes={"measurement": "Histopathology"},
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-export-publication",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
            plausibility="Strong mechanistic rationale.",
        )
    )
    await aop_tools.link_stressor(
        aop_tools.StressorLinkInputModel(
            draft_id="draft-export-publication",
            version_id="v5",
            author="tester",
            summary="link stressor",
            stressor_id="CHEM:PFOS",
            label="Perfluorooctanesulfonic acid",
            source="1763-23-1",
            target="KE:1",
        )
    )

    result = await aop_tools.export_draft_review_artifact(
        aop_tools.ExportDraftReviewArtifactInput(
            draft_id="draft-export-publication",
            format="markdown",
            artifact_profile="publication",
            dtxsid="DTXSID3031864",
            assay_limit=3,
            stressor_limit=5,
            min_hitcall=0.9,
        )
    )

    assert result["format"] == "markdown"
    assert result["artifact_profile"] == "publication"
    assert result["filename"] == "draft_review_draft_export_publication.md"
    assert result["evidence_gap_summary"]["total_gap_count"] >= 1
    assert result["section_titles"] == [
        "Executive Summary",
        "Draft Context",
        "Review Findings",
        "Quantitative Evidence",
        "Evidence Gaps",
        "Chemical Activity Overlay",
        "Recommended Next Actions",
        "Limitations and Interpretation",
    ]
    assert "# Scientific Draft Review:" in result["content"]
    assert "## Executive Summary" in result["content"]
    assert "## Evidence Gaps" in result["content"]
    assert "## Recommended Next Actions" in result["content"]
    assert "## Limitations and Interpretation" in result["content"]


@pytest.mark.asyncio
async def test_export_draft_review_artifact_supports_json(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-export-json",
            title="PXR activation leading to liver steatosis",
            description="Draft export example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-export-json",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-export-json",
            version_id="v3",
            author="tester",
            summary="add ao",
            identifier="KE:2",
            title="Liver steatosis",
            event_role="ao",
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-export-json",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
        )
    )

    result = await aop_tools.export_draft_review_artifact(
        aop_tools.ExportDraftReviewArtifactInput(
            draft_id="draft-export-json",
            format="json",
            assay_limit=3,
            stressor_limit=5,
            min_hitcall=0.9,
        )
    )

    assert result["format"] == "json"
    assert result["artifact_profile"] == "review"
    assert result["filename"] == "draft_review_draft_export_json.json"
    assert result["evidence_gap_summary"]["total_gap_count"] >= 1
    parsed = json.loads(result["content"])
    assert parsed["bundle"]["draft_id"] == "draft-export-json"
    assert "validation" in parsed["bundle"]
    assert "quantitative_review" in parsed["bundle"]
    assert "evidence_gaps" in parsed


@pytest.mark.asyncio
async def test_save_draft_review_artifact_writes_file(monkeypatch, tmp_path) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())
    monkeypatch.setattr(aop_tools, "get_comptox_client", lambda: StubDraftBundleCompTox())
    monkeypatch.setattr(
        aop_tools,
        "get_settings",
        lambda: SimpleNamespace(artifact_output_dir=str(tmp_path)),
    )

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-save",
            title="PXR activation leading to liver steatosis",
            description="Draft save example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-save",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
            attributes={"measurement_methods": ["Reporter assay"]},
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-save",
            version_id="v3",
            author="tester",
            summary="add ao",
            identifier="KE:2",
            title="Liver steatosis",
            event_role="ao",
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-save",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
        )
    )

    result = await aop_tools.save_draft_review_artifact(
        aop_tools.SaveDraftReviewArtifactInput(
            draft_id="draft-save",
            format="markdown",
            artifact_profile="publication",
            subdirectory="handoff/pfAS",
            filename="scientist_review.md",
            assay_limit=3,
            stressor_limit=5,
            min_hitcall=0.9,
        )
    )

    saved_path = tmp_path / "draft_reviews" / "handoff" / "pfAS" / "scientist_review.md"
    metadata_path = tmp_path / "draft_reviews" / "handoff" / "pfAS" / "scientist_review.md.meta.json"
    assert result["format"] == "markdown"
    assert result["artifact_profile"] == "publication"
    assert result["filename"] == "scientist_review.md"
    assert result["path"] == str(saved_path.resolve())
    assert result["relative_path"] == "handoff/pfAS/scientist_review.md"
    assert result["metadata_path"] == str(metadata_path.resolve())
    assert result["output_directory"] == str(saved_path.parent.resolve())
    assert result["bytes_written"] > 0
    assert result["overwrote_existing_file"] is False
    assert result["evidence_gap_summary"]["total_gap_count"] >= 1
    assert saved_path.exists()
    assert metadata_path.exists()
    assert "# Scientific Draft Review:" in saved_path.read_text(encoding="utf-8")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["draft_id"] == "draft-save"
    assert metadata["artifact_profile"] == "publication"
    assert metadata["evidence_gap_summary"]["total_gap_count"] >= 1


@pytest.mark.asyncio
async def test_save_draft_review_artifact_requires_overwrite_flag(monkeypatch, tmp_path) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())
    monkeypatch.setattr(
        aop_tools,
        "get_settings",
        lambda: SimpleNamespace(artifact_output_dir=str(tmp_path)),
    )

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-save-existing",
            title="PXR activation leading to liver steatosis",
            description="Draft save example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )

    first = await aop_tools.save_draft_review_artifact(
        aop_tools.SaveDraftReviewArtifactInput(
            draft_id="draft-save-existing",
            format="json",
            filename="review.json",
            assay_limit=3,
            stressor_limit=5,
            min_hitcall=0.9,
        )
    )

    assert first["overwrote_existing_file"] is False

    with pytest.raises(FileExistsError):
        await aop_tools.save_draft_review_artifact(
            aop_tools.SaveDraftReviewArtifactInput(
                draft_id="draft-save-existing",
                format="json",
                filename="review.json",
                assay_limit=3,
                stressor_limit=5,
                min_hitcall=0.9,
            )
        )


@pytest.mark.asyncio
async def test_list_saved_draft_review_artifacts_returns_saved_files(monkeypatch, tmp_path) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())
    monkeypatch.setattr(
        aop_tools,
        "get_settings",
        lambda: SimpleNamespace(artifact_output_dir=str(tmp_path)),
    )

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-indexed-1",
            title="Indexed draft one",
            description="Draft index example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-indexed-2",
            title="Indexed draft two",
            description="Draft index example.",
            adverse_outcome="Liver fibrosis",
            author="tester",
            summary="create draft",
        )
    )

    await aop_tools.save_draft_review_artifact(
        aop_tools.SaveDraftReviewArtifactInput(
            draft_id="draft-indexed-1",
            format="markdown",
            artifact_profile="publication",
            subdirectory="handoff/a",
            filename="review_a.md",
        )
    )
    await aop_tools.save_draft_review_artifact(
        aop_tools.SaveDraftReviewArtifactInput(
            draft_id="draft-indexed-2",
            format="json",
            artifact_profile="review",
            subdirectory="handoff/b",
            filename="review_b.json",
        )
    )

    result = await aop_tools.list_saved_draft_review_artifacts(
        aop_tools.ListSavedDraftReviewArtifactsInput(
            subdirectory="handoff",
            limit=10,
        )
    )

    assert result["diagnostics"]["artifact_root_directory"] == str((tmp_path / "draft_reviews").resolve())
    assert result["diagnostics"]["scanned_artifact_count"] == 2
    assert result["diagnostics"]["returned_artifact_count"] == 2
    assert result["diagnostics"]["missing_metadata_count"] == 0
    by_filename = {item["filename"]: item for item in result["results"]}
    assert by_filename["review_a.md"]["draft_id"] == "draft-indexed-1"
    assert by_filename["review_a.md"]["artifact_profile"] == "publication"
    assert by_filename["review_a.md"]["metadata_available"] is True
    assert by_filename["review_a.md"]["evidence_gap_summary"]["total_gap_count"] >= 1
    assert by_filename["review_b.json"]["format"] == "json"
    assert by_filename["review_b.json"]["draft_id"] == "draft-indexed-2"

    filtered = await aop_tools.list_saved_draft_review_artifacts(
        aop_tools.ListSavedDraftReviewArtifactsInput(
            draft_id="draft-indexed-1",
            artifact_profile="publication",
            format="markdown",
        )
    )

    assert filtered["diagnostics"]["returned_artifact_count"] == 1
    assert filtered["results"][0]["filename"] == "review_a.md"


@pytest.mark.asyncio
async def test_plan_linear_draft_review_document_from_live_export(monkeypatch) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-linear-live",
            title="PXR activation leading to liver steatosis",
            description="Draft linear handoff example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-linear-live",
            version_id="v2",
            author="tester",
            summary="add mie",
            identifier="KE:1",
            title="Activation, Pregnane-X receptor, NR1I2",
            event_role="mie",
        )
    )
    await aop_tools.add_or_update_ke(
        aop_tools.KeyEventInputModel(
            draft_id="draft-linear-live",
            version_id="v3",
            author="tester",
            summary="add ao",
            identifier="KE:2",
            title="Liver steatosis",
            event_role="ao",
        )
    )
    await aop_tools.add_or_update_ker(
        aop_tools.KerInputModel(
            draft_id="draft-linear-live",
            version_id="v4",
            author="tester",
            summary="add ker",
            identifier="KER:1",
            upstream="KE:1",
            downstream="KE:2",
        )
    )

    result = await aop_tools.plan_linear_draft_review_document(
        aop_tools.PlanLinearDraftReviewDocumentInput(
            draft_id="draft-linear-live",
            artifact_profile="publication",
            project="Tox Reviews",
            issue="AOP-123",
        )
    )

    assert result["source"]["mode"] == "live_draft_export"
    assert result["source"]["draft_id"] == "draft-linear-live"
    assert result["source"]["artifact_profile"] == "publication"
    assert "ready_for_review" in result["artifact_summary"]
    assert result["evidence_gap_summary"]["total_gap_count"] >= 1
    assert result["linear_document"]["project"] == "Tox Reviews"
    assert result["linear_document"]["issue"] == "AOP-123"
    assert result["linear_document"]["title"].startswith("Scientific Draft Review:")
    assert "## Handoff Context" in result["linear_document"]["content"]
    assert result["suggested_create_document_arguments"]["project"] == "Tox Reviews"
    assert result["suggested_create_document_arguments"]["issue"] == "AOP-123"


@pytest.mark.asyncio
async def test_plan_linear_draft_review_document_from_saved_artifact(monkeypatch, tmp_path) -> None:
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)
    monkeypatch.setattr(aop_tools, "get_draft_store", lambda: draft_store)
    monkeypatch.setattr(aop_tools, "get_write_tools", lambda: write_tools)
    monkeypatch.setattr(aop_tools, "get_aop_db_adapter", lambda: StubDraftBundleDbAdapter())
    monkeypatch.setattr(
        aop_tools,
        "get_settings",
        lambda: SimpleNamespace(artifact_output_dir=str(tmp_path)),
    )

    await aop_tools.create_draft_aop(
        aop_tools.CreateDraftInputModel(
            draft_id="draft-linear-saved",
            title="PXR activation leading to liver steatosis",
            description="Draft linear handoff example.",
            adverse_outcome="Liver steatosis",
            author="tester",
            summary="create draft",
        )
    )

    saved = await aop_tools.save_draft_review_artifact(
        aop_tools.SaveDraftReviewArtifactInput(
            draft_id="draft-linear-saved",
            format="markdown",
            artifact_profile="publication",
            subdirectory="handoff/linear",
            filename="review.md",
        )
    )

    result = await aop_tools.plan_linear_draft_review_document(
        aop_tools.PlanLinearDraftReviewDocumentInput(
            artifact_relative_path=saved["relative_path"],
            project="Tox Reviews",
        )
    )

    assert result["source"]["mode"] == "saved_artifact"
    assert result["source"]["relative_path"] == "handoff/linear/review.md"
    assert result["source"]["metadata_available"] is True
    assert result["linear_document"]["source_reference"] == "handoff/linear/review.md"
    assert result["linear_document"]["project"] == "Tox Reviews"
    assert result["evidence_gap_summary"]["total_gap_count"] >= 1
    assert "## Handoff Context" in result["linear_document"]["content"]
    assert "Saved artifact" in result["linear_document"]["content"]
    assert result["warnings"] == []
