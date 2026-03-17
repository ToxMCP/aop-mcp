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


class StubDbAdapter:
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
                        "stressor_labels": ["PFOS"],
                    },
                    {
                        "preferred_name": "DBDPE",
                        "dtxsid": "DTXSID9999999",
                        "casrn": "84852-53-9",
                        "stressor_labels": ["DBDPE"],
                    },
                ],
                "max_hitcall": 1.0,
            }
        ]


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
