from __future__ import annotations

import pytest

from src.server.tools import aop as aop_tools


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
