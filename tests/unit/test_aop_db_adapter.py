from __future__ import annotations

import asyncio

import httpx
import pytest

from src.adapters import AOPDBAdapter, CompToxError, SparqlClient
from src.adapters.aop_db import _derive_key_event_search_terms


def make_client(handler: httpx.MockTransport) -> SparqlClient:
    return SparqlClient(["https://sparql.example/aopdb"], transport=handler)


@pytest.mark.asyncio
async def test_map_chemical_to_aops_returns_records() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert 'CONTAINS(LCASE(?stressorLabel), LCASE("PFOS"))' in request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "aop": {"value": "http://aopwiki.org/aops/10"},
                            "title": {"value": "Liver steatosis"},
                            "stressId": {"value": "DSS:100"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client)
        records = await adapter.map_chemical_to_aops(name="PFOS")

    assert records == [
        {
            "aop": {
                "id": "AOP:10",
                "iri": "http://aopwiki.org/aops/10",
                "title": "Liver steatosis",
            },
            "stressor_id": "DSS:100",
        }
    ]


@pytest.mark.asyncio
async def test_map_assay_to_aops_requires_id() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client)
        with pytest.raises(ValueError):
            await adapter.map_assay_to_aops("")


@pytest.mark.asyncio
async def test_map_assay_to_aops_returns_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "BIND(\"HTS123\" AS ?assayId)" in request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "aop": {"value": "http://aopwiki.org/aops/25"},
                            "title": {"value": "Neurotoxicity"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client)
        records = await adapter.map_assay_to_aops("HTS123")

    assert records == [
        {
            "aop": {
                "id": "AOP:25",
                "iri": "http://aopwiki.org/aops/25",
                "title": "Neurotoxicity",
            },
            "assay_id": "HTS123",
        }
    ]


class StubCompTox:
    has_api_key = True

    def search_equal(self, value: str):
        assert value == "1763-23-1"
        return [
            {
                "dtxsid": "DTXSID3031864",
                "casrn": "1763-23-1",
                "preferredName": "Perfluorooctanesulfonic acid",
            }
        ]

    def bioactivity_data_by_dtxsid(self, dtxsid: str):
        assert dtxsid == "DTXSID3031864"
        return [
            {"aeid": 2309, "hitc": 0.98, "coff": 20.0},
            {"aeid": 2309, "hitc": 0.40, "coff": 50.0},
            {"aeid": 9999, "hitc": 0.50, "coff": 10.0},
        ]

    def assay_by_aeid(self, aeid: int):
        assert aeid == 2309
        return {
            "assayName": "CCTE_GLTED_hDIO1",
            "assayComponentEndpointName": "CCTE_GLTED_hDIO1",
            "assayComponentEndpointDesc": "DIO1 activity assay",
            "assayFunctionType": "enzymatic activity",
            "intendedTargetFamily": "deiodinase",
            "intendedTargetFamilySub": "deiodinase Type 1",
            "gene": [{"geneSymbol": "DIO1"}],
        }


class NoApiKeyCompTox:
    has_api_key = False


@pytest.mark.asyncio
async def test_list_assays_for_aop_returns_ranked_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        assert "aopo:has_chemical_entity ?chemicalEntity" in query
        assert "<https://identifiers.org/aop/529>" in query
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                            "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                            "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=StubCompTox())
        records = await adapter.list_assays_for_aop("AOP:529", limit=10, min_hitcall=0.9)

    assert records == [
        {
            "aeid": 2309,
            "assay_name": "CCTE_GLTED_hDIO1",
            "assay_component_endpoint_name": "CCTE_GLTED_hDIO1",
            "assay_component_endpoint_desc": "DIO1 activity assay",
            "assay_function_type": "enzymatic activity",
            "target_family": "deiodinase",
            "target_family_sub": "deiodinase Type 1",
            "gene_symbols": ["DIO1"],
            "specificity_score": None,
            "support_count": 1,
            "max_hitcall": 0.98,
            "supporting_chemicals": [
                {
                    "dtxsid": "DTXSID3031864",
                    "casrn": "1763-23-1",
                    "preferred_name": "Perfluorooctanesulfonic acid",
                    "stressor_id": "https://identifiers.org/aop.stressor/771",
                    "stressor_label": "Perfluorooctanesulfonic acid",
                    "hitcall": 0.98,
                    "activity_cutoff": 20.0,
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_list_assays_for_aop_with_diagnostics_reports_pipeline_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                            "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                            "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=StubCompTox())
        report = await adapter.list_assays_for_aop_with_diagnostics(
            "AOP:529",
            limit=10,
            min_hitcall=0.9,
        )

    assert report["results"][0]["aeid"] == 2309
    assert report["diagnostics"] == {
        "aop_id": "AOP:529",
        "comptox_api_key_configured": True,
        "stressor_count": 1,
        "chemical_match_count": 1,
        "bioactivity_hit_count": 1,
        "returned_assay_count": 1,
        "empty_reason": None,
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_list_assays_for_aop_with_diagnostics_reports_missing_api_key() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=NoApiKeyCompTox())
        report = await adapter.list_assays_for_aop_with_diagnostics("AOP:529")

    assert report["results"] == []
    assert report["diagnostics"]["empty_reason"] == "missing_comptox_api_key"
    assert report["diagnostics"]["comptox_api_key_configured"] is False


@pytest.mark.asyncio
async def test_list_assays_for_aop_with_diagnostics_reports_no_linked_stressors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=StubCompTox())
        report = await adapter.list_assays_for_aop_with_diagnostics("AOP:529")

    assert report["results"] == []
    assert report["diagnostics"]["stressor_count"] == 0
    assert report["diagnostics"]["empty_reason"] == "no_linked_stressors"


@pytest.mark.asyncio
async def test_list_assays_for_aop_with_diagnostics_reports_no_comptox_match() -> None:
    class NoChemicalMatchCompTox(StubCompTox):
        def search_equal(self, value: str):
            return []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                            "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                            "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=NoChemicalMatchCompTox())
        report = await adapter.list_assays_for_aop_with_diagnostics("AOP:529")

    assert report["results"] == []
    assert report["diagnostics"]["chemical_match_count"] == 0
    assert report["diagnostics"]["empty_reason"] == "no_comptox_chemical_match"


@pytest.mark.asyncio
async def test_list_assays_for_aop_with_diagnostics_reports_no_bioactivity_hits() -> None:
    class NoBioactivityHitsCompTox(StubCompTox):
        def bioactivity_data_by_dtxsid(self, dtxsid: str):
            return [{"aeid": 2309, "hitc": 0.5, "coff": 20.0}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                            "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                            "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=NoBioactivityHitsCompTox())
        report = await adapter.list_assays_for_aop_with_diagnostics(
            "AOP:529",
            min_hitcall=0.9,
        )

    assert report["results"] == []
    assert report["diagnostics"]["chemical_match_count"] == 1
    assert report["diagnostics"]["bioactivity_hit_count"] == 0
    assert report["diagnostics"]["empty_reason"] == "no_bioactivity_hits_after_filtering"


@pytest.mark.asyncio
async def test_list_assays_for_aops_aggregates_by_aeid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        if "<https://identifiers.org/aop/529>" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                                "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                                "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                            }
                        ]
                    }
                },
            )
        if "<https://identifiers.org/aop/517>" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "stressor": {"value": "https://identifiers.org/aop.stressor/900"},
                                "stressorLabel": {"value": "Perfluorooctanoic acid"},
                                "chemicalEntity": {"value": "https://identifiers.org/cas/335-67-1"},
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"Unexpected query: {query}")

    class AggregatingCompTox(StubCompTox):
        def search_equal(self, value: str):
            if value == "1763-23-1":
                return [
                    {
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "preferredName": "Perfluorooctanesulfonic acid",
                    }
                ]
            if value == "335-67-1":
                return [
                    {
                        "dtxsid": "DTXSID8031865",
                        "casrn": "335-67-1",
                        "preferredName": "Perfluorooctanoic acid",
                    }
                ]
            raise AssertionError(f"Unexpected search value: {value}")

        def bioactivity_data_by_dtxsid(self, dtxsid: str):
            if dtxsid == "DTXSID3031864":
                return [
                    {"aeid": 2309, "hitc": 0.98, "coff": 20.0},
                    {"aeid": 4000, "hitc": 0.95, "coff": 15.0},
                ]
            if dtxsid == "DTXSID8031865":
                return [
                    {"aeid": 2309, "hitc": 0.97, "coff": 18.0},
                    {"aeid": 5000, "hitc": 0.96, "coff": 12.0},
                ]
            raise AssertionError(f"Unexpected dtxsid: {dtxsid}")

        def assay_by_aeid(self, aeid: int):
            assay_names = {
                2309: "CCTE_GLTED_hDIO1",
                4000: "PFOS_secondary",
                5000: "PFOA_secondary",
            }
            return {
                "assayName": assay_names[aeid],
                "assayComponentEndpointName": assay_names[aeid],
                "assayComponentEndpointDesc": f"{assay_names[aeid]} description",
                "assayFunctionType": "enzymatic activity",
                "intendedTargetFamily": "deiodinase",
                "intendedTargetFamilySub": "deiodinase Type 1",
                "gene": [{"geneSymbol": "DIO1"}],
            }

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=AggregatingCompTox())
        records = await adapter.list_assays_for_aops(
            ["AOP:529", "AOP:517"],
            limit=10,
            per_aop_limit=10,
            min_hitcall=0.9,
        )

    assert records[0]["aeid"] == 2309
    assert records[0]["aop_support_count"] == 2
    assert records[0]["chemical_support_count"] == 2
    assert records[0]["supporting_aops"] == ["AOP:517", "AOP:529"]
    assert [chemical["preferred_name"] for chemical in records[0]["supporting_chemicals"]] == [
        "Perfluorooctanesulfonic acid",
        "Perfluorooctanoic acid",
    ]
    assert [record["aeid"] for record in records[:3]] == [2309, 5000, 4000]


@pytest.mark.asyncio
async def test_list_assays_for_aops_with_diagnostics_tracks_per_aop_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        if "<https://identifiers.org/aop/529>" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                                "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                                "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                            }
                        ]
                    }
                },
            )
        if "<https://identifiers.org/aop/517>" in query:
            return httpx.Response(200, json={"results": {"bindings": []}})
        raise AssertionError(f"Unexpected query: {query}")

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=StubCompTox())
        report = await adapter.list_assays_for_aops_with_diagnostics(
            ["AOP:529", "AOP:517", "AOP:529"],
            limit=10,
            per_aop_limit=10,
            min_hitcall=0.9,
        )

    assert report["results"][0]["aeid"] == 2309
    assert report["diagnostics"]["requested_aop_ids"] == ["AOP:529", "AOP:517", "AOP:529"]
    assert report["diagnostics"]["processed_aop_ids"] == ["AOP:529", "AOP:517"]
    assert report["diagnostics"]["returned_assay_count"] == 1
    assert report["diagnostics"]["per_aop"][0]["empty_reason"] is None
    assert report["diagnostics"]["per_aop"][1]["empty_reason"] == "no_linked_stressors"
    assert "Duplicate AOP identifiers were deduplicated before aggregation." in report["diagnostics"]["warnings"]


@pytest.mark.asyncio
async def test_discover_orphan_stressors_for_aop_returns_multi_assay_candidates_and_excludes_curated_stressors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        assert "<https://identifiers.org/aop/529>" in query
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                            "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                            "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                        }
                    ]
                }
            },
        )

    class OrphanDiscoveryCompTox(StubCompTox):
        def search_equal(self, value: str):
            if value in {"1763-23-1", "Perfluorooctanesulfonic acid"}:
                return [
                    {
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "preferredName": "Perfluorooctanesulfonic acid",
                    }
                ]
            raise AssertionError(f"Unexpected search value: {value}")

        def bioactivity_data_by_dtxsid(self, dtxsid: str):
            assert dtxsid == "DTXSID3031864"
            return [
                {"aeid": 101, "hitc": 0.98, "coff": 12.0},
                {"aeid": 202, "hitc": 0.97, "coff": 20.0},
            ]

        def assay_by_aeid(self, aeid: int):
            assays = {
                101: {
                    "assayName": "ATG_PXRE_CIS",
                    "assayComponentEndpointName": "ATG_PXRE_CIS",
                    "assayComponentEndpointDesc": "PXR reporter assay",
                    "assayFunctionType": "reporter gene",
                    "intendedTargetFamily": "nuclear receptor",
                    "intendedTargetFamilySub": "PXR",
                    "gene": [{"geneSymbol": "NR1I2"}],
                    "multi_conc_assay_chemical_count_active": 100,
                    "multi_conc_assay_chemical_count_total": 500,
                },
                202: {
                    "assayName": "HTS_PXR_CONFIRM",
                    "assayComponentEndpointName": "HTS_PXR_CONFIRM",
                    "assayComponentEndpointDesc": "PXR confirmation assay",
                    "assayFunctionType": "binding",
                    "intendedTargetFamily": "nuclear receptor",
                    "intendedTargetFamilySub": "PXR",
                    "gene": [{"geneSymbol": "NR1I2"}],
                    "multi_conc_assay_chemical_count_active": 300,
                    "multi_conc_assay_chemical_count_total": 500,
                },
            }
            return assays[aeid]

        def get_chemicals_in_assay(self, aeid: str):
            if aeid == "101":
                return [
                    {
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "preferredName": "Perfluorooctanesulfonic acid",
                    },
                    {
                        "dtxsid": "DTXSID0000001",
                        "casrn": "111-11-1",
                        "preferredName": "Alpha candidate",
                    },
                    {
                        "dtxsid": "DTXSID0000002",
                        "casrn": "222-22-2",
                        "preferredName": "Beta candidate",
                    },
                ]
            if aeid == "202":
                return [
                    {
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "preferredName": "Perfluorooctanesulfonic acid",
                    },
                    "DTXSID3031864",
                    {
                        "dtxsid": "DTXSID0000001",
                        "casrn": "111-11-1",
                        "preferredName": "Alpha candidate",
                    },
                    {
                        "dtxsid": "DTXSID0000003",
                        "casrn": "333-33-3",
                        "preferredName": "Gamma candidate",
                    },
                ]
            raise AssertionError(f"Unexpected AEID: {aeid}")

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=OrphanDiscoveryCompTox())
        report = await adapter.discover_orphan_stressors_for_aop_with_diagnostics(
            "AOP:529",
            assay_limit=5,
            per_assay_chemical_limit=10,
            limit=5,
            min_hitcall=0.9,
        )

    assert [row["preferred_name"] for row in report["results"]] == [
        "Alpha candidate",
        "Beta candidate",
        "Gamma candidate",
    ]
    assert report["results"][0]["supporting_assay_count"] == 2
    assert report["results"][0]["best_assay_rank"] == 1
    assert report["results"][0]["supporting_assays"] == [
        {
            "aeid": 101,
            "assay_name": "ATG_PXRE_CIS",
            "rank": 1,
            "specificity_score": 0.8,
        },
        {
            "aeid": 202,
            "assay_name": "HTS_PXR_CONFIRM",
            "rank": 2,
            "specificity_score": 0.4,
        },
    ]
    assert report["diagnostics"] == {
        "aop_id": "AOP:529",
        "comptox_api_key_configured": True,
        "curated_stressor_count": 1,
        "curated_chemical_match_count": 1,
        "assay_candidate_count": 2,
        "scanned_assay_count": 2,
        "assay_chemical_hit_count": 7,
        "returned_candidate_count": 3,
        "empty_reason": None,
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_discover_orphan_stressors_for_aop_reports_empty_after_excluding_curated_chemicals() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                            "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                            "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                        }
                    ]
                }
            },
        )

    class CuratedOnlyCompTox(StubCompTox):
        def search_equal(self, value: str):
            if value in {"1763-23-1", "Perfluorooctanesulfonic acid"}:
                return [
                    {
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "preferredName": "Perfluorooctanesulfonic acid",
                    }
                ]
            raise AssertionError(f"Unexpected search value: {value}")

        def bioactivity_data_by_dtxsid(self, dtxsid: str):
            return [{"aeid": 101, "hitc": 0.98, "coff": 12.0}]

        def assay_by_aeid(self, aeid: int):
            return {
                "assayName": "ATG_PXRE_CIS",
                "assayComponentEndpointName": "ATG_PXRE_CIS",
                "assayComponentEndpointDesc": "PXR reporter assay",
                "assayFunctionType": "reporter gene",
                "intendedTargetFamily": "nuclear receptor",
                "intendedTargetFamilySub": "PXR",
                "gene": [{"geneSymbol": "NR1I2"}],
                "multi_conc_assay_chemical_count_active": 100,
                "multi_conc_assay_chemical_count_total": 500,
            }

        def get_chemicals_in_assay(self, aeid: str):
            return [
                {
                    "dtxsid": "DTXSID3031864",
                    "casrn": "1763-23-1",
                    "preferredName": "Perfluorooctanesulfonic acid",
                }
            ]

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=CuratedOnlyCompTox())
        report = await adapter.discover_orphan_stressors_for_aop_with_diagnostics("AOP:529")

    assert report["results"] == []
    assert report["diagnostics"]["assay_chemical_hit_count"] == 1
    assert report["diagnostics"]["empty_reason"] == "no_orphan_candidates_after_excluding_curated_chemicals"


@pytest.mark.asyncio
async def test_discover_orphan_stressors_for_aop_prioritizes_specific_non_background_assays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=StubCompTox())

        async def fake_list_stressors(aop_id: str) -> list[dict[str, str]]:
            assert aop_id == "AOP:529"
            return [
                {
                    "stressor_id": "https://identifiers.org/aop.stressor/771",
                    "stressor_label": "Perfluorooctanesulfonic acid",
                    "chemical_entity": "1763-23-1",
                }
            ]

        async def fake_build_curated_index(_stressors: list[dict[str, str]]) -> tuple[dict[str, set[str]], int, list[str]]:
            return (
                {
                    "dtxsids": set(),
                    "casrns": set(),
                    "names": set(),
                },
                0,
                [],
            )

        async def fake_list_assays_for_aop_with_diagnostics(
            aop_id: str,
            *,
            limit: int = 25,
            min_hitcall: float = 0.9,
        ) -> dict[str, object]:
            assert aop_id == "AOP:529"
            assert limit == 1
            assert min_hitcall == 0.9
            return {
                "results": [
                    {
                        "aeid": 101,
                        "assay_name": "Background control assay",
                        "assay_function_type": "background control",
                        "target_family": "cell morphology",
                        "gene_symbols": [],
                        "specificity_score": None,
                        "support_count": 10,
                        "max_hitcall": 0.99,
                    },
                    {
                        "aeid": 202,
                        "assay_name": "Mechanistic reporter assay",
                        "assay_function_type": "reporter gene",
                        "target_family": "nuclear receptor",
                        "gene_symbols": ["NR1I2"],
                        "specificity_score": 0.8,
                        "support_count": 1,
                        "max_hitcall": 0.95,
                    },
                ],
                "diagnostics": {
                    "warnings": [],
                    "empty_reason": None,
                },
            }

        scanned_aeids: list[int | str] = []

        async def fake_fetch_orphan_assay_chemicals(aeid: int | str) -> list[dict[str, str]]:
            scanned_aeids.append(aeid)
            return [
                {
                    "dtxsid": "DTXSID0001234",
                    "casrn": "123-45-6",
                    "preferredName": "Mechanistic candidate",
                }
            ]

        monkeypatch.setattr(adapter, "_list_stressor_chemicals_for_aop", fake_list_stressors)
        monkeypatch.setattr(adapter, "_build_curated_chemical_index", fake_build_curated_index)
        monkeypatch.setattr(adapter, "list_assays_for_aop_with_diagnostics", fake_list_assays_for_aop_with_diagnostics)
        monkeypatch.setattr(adapter, "_fetch_orphan_assay_chemicals", fake_fetch_orphan_assay_chemicals)

        report = await adapter.discover_orphan_stressors_for_aop_with_diagnostics(
            "AOP:529",
            assay_limit=1,
            per_assay_chemical_limit=5,
            limit=5,
            min_hitcall=0.9,
        )

    assert scanned_aeids == [202]
    assert report["results"] == [
        {
            "dtxsid": "DTXSID0001234",
            "casrn": "123-45-6",
            "preferred_name": "Mechanistic candidate",
            "supporting_assay_count": 1,
            "best_assay_rank": 1,
            "max_specificity_score": 0.8,
            "supporting_assays": [
                {
                    "aeid": 202,
                    "assay_name": "Mechanistic reporter assay",
                    "rank": 1,
                    "specificity_score": 0.8,
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_discover_orphan_stressors_for_aop_times_out_assay_chemical_fetches_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(
            client,
            comptox_client=StubCompTox(),
            orphan_assay_chemical_timeout_seconds=0.01,
        )

        async def fake_list_stressors(aop_id: str) -> list[dict[str, str]]:
            assert aop_id == "AOP:529"
            return [
                {
                    "stressor_id": "https://identifiers.org/aop.stressor/771",
                    "stressor_label": "Perfluorooctanesulfonic acid",
                    "chemical_entity": "1763-23-1",
                }
            ]

        async def fake_build_curated_index(_stressors: list[dict[str, str]]) -> tuple[dict[str, set[str]], int, list[str]]:
            return (
                {
                    "dtxsids": set(),
                    "casrns": set(),
                    "names": set(),
                },
                0,
                [],
            )

        async def fake_list_assays_for_aop_with_diagnostics(
            aop_id: str,
            *,
            limit: int = 25,
            min_hitcall: float = 0.9,
        ) -> dict[str, object]:
            assert aop_id == "AOP:529"
            return {
                "results": [
                    {
                        "aeid": 303,
                        "assay_name": "Slow remote assay",
                        "assay_function_type": "reporter gene",
                        "target_family": "nuclear receptor",
                        "gene_symbols": ["NR1I2"],
                        "specificity_score": 0.7,
                        "support_count": 1,
                        "max_hitcall": 0.96,
                    }
                ],
                "diagnostics": {
                    "warnings": [],
                    "empty_reason": None,
                },
            }

        async def fake_call_comptox(method_name: str, *args: object) -> list[dict[str, str]]:
            assert method_name == "get_chemicals_in_assay"
            assert args == ("303",)
            await asyncio.sleep(0.05)
            return [
                {
                    "dtxsid": "DTXSID0009999",
                    "casrn": "999-99-9",
                    "preferredName": "Late candidate",
                }
            ]

        monkeypatch.setattr(adapter, "_list_stressor_chemicals_for_aop", fake_list_stressors)
        monkeypatch.setattr(adapter, "_build_curated_chemical_index", fake_build_curated_index)
        monkeypatch.setattr(adapter, "list_assays_for_aop_with_diagnostics", fake_list_assays_for_aop_with_diagnostics)
        monkeypatch.setattr(adapter, "_call_comptox", fake_call_comptox)

        report = await adapter.discover_orphan_stressors_for_aop_with_diagnostics(
            "AOP:529",
            assay_limit=1,
            per_assay_chemical_limit=5,
            limit=5,
            min_hitcall=0.9,
        )

    assert report["results"] == []
    assert report["diagnostics"]["assay_chemical_hit_count"] == 0
    assert report["diagnostics"]["empty_reason"] == "no_assay_chemical_hits"
    assert any(
        "CompTox assay-chemical lookup failed for AEID 303" in warning
        for warning in report["diagnostics"]["warnings"]
    )
    assert any(
        "did not return any active chemicals from CompTox" in warning
        for warning in report["diagnostics"]["warnings"]
    )


@pytest.mark.asyncio
async def test_discover_orphan_stressors_for_aops_aggregates_cross_pathway_support() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        if "<https://identifiers.org/aop/529>" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                                "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                                "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                            }
                        ]
                    }
                },
            )
        if "<https://identifiers.org/aop/517>" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "stressor": {"value": "https://identifiers.org/aop.stressor/900"},
                                "stressorLabel": {"value": "Perfluorooctanoic acid"},
                                "chemicalEntity": {"value": "https://identifiers.org/cas/335-67-1"},
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"Unexpected query: {query}")

    class MultiAopOrphanCompTox(StubCompTox):
        def search_equal(self, value: str):
            lookup = {
                "1763-23-1": {
                    "dtxsid": "DTXSID3031864",
                    "casrn": "1763-23-1",
                    "preferredName": "Perfluorooctanesulfonic acid",
                },
                "Perfluorooctanesulfonic acid": {
                    "dtxsid": "DTXSID3031864",
                    "casrn": "1763-23-1",
                    "preferredName": "Perfluorooctanesulfonic acid",
                },
                "335-67-1": {
                    "dtxsid": "DTXSID8031865",
                    "casrn": "335-67-1",
                    "preferredName": "Perfluorooctanoic acid",
                },
                "Perfluorooctanoic acid": {
                    "dtxsid": "DTXSID8031865",
                    "casrn": "335-67-1",
                    "preferredName": "Perfluorooctanoic acid",
                },
            }
            if value not in lookup:
                raise AssertionError(f"Unexpected search value: {value}")
            return [lookup[value]]

        def bioactivity_data_by_dtxsid(self, dtxsid: str):
            if dtxsid == "DTXSID3031864":
                return [
                    {"aeid": 101, "hitc": 0.98, "coff": 12.0},
                    {"aeid": 202, "hitc": 0.97, "coff": 20.0},
                ]
            if dtxsid == "DTXSID8031865":
                return [
                    {"aeid": 202, "hitc": 0.99, "coff": 11.0},
                    {"aeid": 303, "hitc": 0.96, "coff": 14.0},
                ]
            raise AssertionError(f"Unexpected dtxsid: {dtxsid}")

        def assay_by_aeid(self, aeid: int):
            assays = {
                101: {
                    "assayName": "ATG_PXRE_CIS",
                    "assayComponentEndpointName": "ATG_PXRE_CIS",
                    "assayComponentEndpointDesc": "PXR reporter assay",
                    "assayFunctionType": "reporter gene",
                    "intendedTargetFamily": "nuclear receptor",
                    "intendedTargetFamilySub": "PXR",
                    "gene": [{"geneSymbol": "NR1I2"}],
                    "multi_conc_assay_chemical_count_active": 100,
                    "multi_conc_assay_chemical_count_total": 500,
                },
                202: {
                    "assayName": "HTS_PXR_CONFIRM",
                    "assayComponentEndpointName": "HTS_PXR_CONFIRM",
                    "assayComponentEndpointDesc": "PXR confirmation assay",
                    "assayFunctionType": "binding",
                    "intendedTargetFamily": "nuclear receptor",
                    "intendedTargetFamilySub": "PXR",
                    "gene": [{"geneSymbol": "NR1I2"}],
                    "multi_conc_assay_chemical_count_active": 300,
                    "multi_conc_assay_chemical_count_total": 500,
                },
                303: {
                    "assayName": "HTS_PXR_ALT",
                    "assayComponentEndpointName": "HTS_PXR_ALT",
                    "assayComponentEndpointDesc": "Alternative PXR assay",
                    "assayFunctionType": "binding",
                    "intendedTargetFamily": "nuclear receptor",
                    "intendedTargetFamilySub": "PXR",
                    "gene": [{"geneSymbol": "NR1I2"}],
                    "multi_conc_assay_chemical_count_active": 50,
                    "multi_conc_assay_chemical_count_total": 500,
                },
            }
            return assays[aeid]

        def get_chemicals_in_assay(self, aeid: str):
            if aeid == "101":
                return [
                    {
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "preferredName": "Perfluorooctanesulfonic acid",
                    },
                    {
                        "dtxsid": "DTXSID0000001",
                        "casrn": "111-11-1",
                        "preferredName": "Alpha candidate",
                    },
                ]
            if aeid == "202":
                return [
                    {
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "preferredName": "Perfluorooctanesulfonic acid",
                    },
                    {
                        "dtxsid": "DTXSID8031865",
                        "casrn": "335-67-1",
                        "preferredName": "Perfluorooctanoic acid",
                    },
                    {
                        "casrn": "111-11-1",
                        "preferredName": "Alpha candidate",
                    },
                    {
                        "dtxsid": "DTXSID0000003",
                        "casrn": "333-33-3",
                        "preferredName": "Gamma candidate",
                    },
                ]
            if aeid == "303":
                return [
                    {
                        "dtxsid": "DTXSID8031865",
                        "casrn": "335-67-1",
                        "preferredName": "Perfluorooctanoic acid",
                    },
                    {
                        "dtxsid": "DTXSID0000004",
                        "casrn": "444-44-4",
                        "preferredName": "Delta candidate",
                    },
                ]
            raise AssertionError(f"Unexpected AEID: {aeid}")

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=MultiAopOrphanCompTox())
        report = await adapter.discover_orphan_stressors_for_aops_with_diagnostics(
            ["AOP:529", "AOP:517", "AOP:529"],
            limit=10,
            per_aop_limit=5,
            per_assay_chemical_limit=10,
            min_hitcall=0.9,
        )

    assert [row["preferred_name"] for row in report["results"]] == [
        "Alpha candidate",
        "Gamma candidate",
        "Delta candidate",
    ]
    assert report["results"][0]["aop_support_count"] == 2
    assert report["results"][0]["supporting_aops"] == ["AOP:517", "AOP:529"]
    assert report["results"][0]["supporting_assay_count"] == 3
    assert report["results"][0]["supporting_assays"] == [
        {
            "aop_id": "AOP:529",
            "aeid": 101,
            "assay_name": "ATG_PXRE_CIS",
            "rank": 1,
            "specificity_score": 0.8,
        },
        {
            "aop_id": "AOP:517",
            "aeid": 202,
            "assay_name": "HTS_PXR_CONFIRM",
            "rank": 2,
            "specificity_score": 0.4,
        },
        {
            "aop_id": "AOP:529",
            "aeid": 202,
            "assay_name": "HTS_PXR_CONFIRM",
            "rank": 2,
            "specificity_score": 0.4,
        },
    ]
    assert report["diagnostics"]["requested_aop_ids"] == ["AOP:529", "AOP:517", "AOP:529"]
    assert report["diagnostics"]["processed_aop_ids"] == ["AOP:529", "AOP:517"]
    assert report["diagnostics"]["returned_candidate_count"] == 3
    assert report["diagnostics"]["per_aop"][0]["returned_candidate_count"] == 3
    assert report["diagnostics"]["per_aop"][1]["returned_candidate_count"] == 4
    assert report["diagnostics"]["warnings"] == [
        "Duplicate AOP identifiers were deduplicated before orphan-candidate aggregation."
    ]


@pytest.mark.asyncio
async def test_list_assays_for_aops_prefers_specific_assay_when_aggregate_support_ties() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        if "<https://identifiers.org/aop/529>" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                                "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                                "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                            }
                        ]
                    }
                },
            )
        if "<https://identifiers.org/aop/517>" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "stressor": {"value": "https://identifiers.org/aop.stressor/900"},
                                "stressorLabel": {"value": "Perfluorooctanoic acid"},
                                "chemicalEntity": {"value": "https://identifiers.org/cas/335-67-1"},
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"Unexpected query: {query}")

    class AggregateSpecificityCompTox(StubCompTox):
        def search_equal(self, value: str):
            if value == "1763-23-1":
                return [
                    {
                        "dtxsid": "DTXSID3031864",
                        "casrn": "1763-23-1",
                        "preferredName": "Perfluorooctanesulfonic acid",
                    }
                ]
            if value == "335-67-1":
                return [
                    {
                        "dtxsid": "DTXSID8031865",
                        "casrn": "335-67-1",
                        "preferredName": "Perfluorooctanoic acid",
                    }
                ]
            raise AssertionError(f"Unexpected search value: {value}")

        def bioactivity_data_by_dtxsid(self, dtxsid: str):
            if dtxsid == "DTXSID3031864":
                return [
                    {"aeid": 2309, "hitc": 0.98, "coff": 20.0},
                    {"aeid": 4000, "hitc": 0.99, "coff": 15.0},
                ]
            if dtxsid == "DTXSID8031865":
                return [
                    {"aeid": 2309, "hitc": 0.97, "coff": 18.0},
                    {"aeid": 5000, "hitc": 0.96, "coff": 12.0},
                ]
            raise AssertionError(f"Unexpected dtxsid: {dtxsid}")

        def assay_by_aeid(self, aeid: int):
            assays = {
                2309: {
                    "assayName": "Shared assay",
                    "assayComponentEndpointName": "Shared assay",
                    "assayComponentEndpointDesc": "Shared assay description",
                    "assayFunctionType": "enzymatic activity",
                    "intendedTargetFamily": "deiodinase",
                    "intendedTargetFamilySub": "deiodinase Type 1",
                    "gene": [{"geneSymbol": "DIO1"}],
                    "multiConcActives": "50/1000(5.00%)",
                },
                4000: {
                    "assayName": "Promiscuous aggregate assay",
                    "assayComponentEndpointName": "Promiscuous aggregate assay",
                    "assayComponentEndpointDesc": "Promiscuous assay description",
                    "assayFunctionType": "enzymatic activity",
                    "intendedTargetFamily": "deiodinase",
                    "intendedTargetFamilySub": "deiodinase Type 1",
                    "gene": [{"geneSymbol": "DIO1"}],
                    "multiConcActives": "800/1000(80.00%)",
                },
                5000: {
                    "assayName": "Specific aggregate assay",
                    "assayComponentEndpointName": "Specific aggregate assay",
                    "assayComponentEndpointDesc": "Specific assay description",
                    "assayFunctionType": "enzymatic activity",
                    "intendedTargetFamily": "deiodinase",
                    "intendedTargetFamilySub": "deiodinase Type 1",
                    "gene": [{"geneSymbol": "DIO1"}],
                    "multiConcActives": "20/1000(2.00%)",
                },
            }
            return assays[aeid]

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=AggregateSpecificityCompTox())
        records = await adapter.list_assays_for_aops(
            ["AOP:529", "AOP:517"],
            limit=10,
            per_aop_limit=10,
            min_hitcall=0.9,
        )

    assert [record["aeid"] for record in records[:3]] == [2309, 5000, 4000]
    assert records[1]["specificity_score"] > records[2]["specificity_score"]


@pytest.mark.asyncio
async def test_search_assays_for_key_event_derives_terms_and_returns_ranked_results() -> None:
    class KeyEventSearchCompTox:
        def search_assay_catalog(self, *, gene_symbols=None, phrases=None, preferred_taxa=None, limit=25):
            assert gene_symbols == ["NR1I2", "PXR"]
            assert phrases == ["pregnane x receptor"]
            assert preferred_taxa == []
            assert limit == 5
            return [
                {
                    "aeid": 103,
                    "assay_name": "ATG_PXRE_CIS",
                    "gene_symbols": ["NR1I2"],
                    "match_score": 245,
                    "match_basis": ["gene_symbol_exact", "gene_name_exact"],
                    "matched_terms": ["NR1I2", "pregnane x receptor"],
                    "source": "comptox_assay_catalog",
                }
            ]

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=KeyEventSearchCompTox())
        result = await adapter.search_assays_for_key_event(
            {
                "id": "KE:239",
                "title": "Activation, Pregnane-X receptor, NR1I2",
                "short_name": "PXR activation",
                "description": "Pregnane X receptor activation event.",
            },
            limit=5,
        )

    assert result["derived_search_terms"] == {
        "structured_gene_identifiers": [],
        "resolved_gene_symbols": [],
        "gene_symbols": ["NR1I2", "PXR"],
        "phrases": ["pregnane x receptor"],
    }
    assert len(result["limitations"]) == 1
    assert result["results"][0]["aeid"] == 103


@pytest.mark.asyncio
async def test_search_assays_for_key_event_reports_phrase_only_matching() -> None:
    class PhraseOnlyCompTox:
        def search_assay_catalog(self, *, gene_symbols=None, phrases=None, preferred_taxa=None, limit=25):
            assert gene_symbols == []
            assert phrases == ["liver steatosis", "steatosis", "fatty liver"]
            assert preferred_taxa == []
            return []

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=PhraseOnlyCompTox())
        result = await adapter.search_assays_for_key_event(
            {
                "id": "KE:999",
                "title": "Increase, liver steatosis",
                "short_name": None,
                "description": None,
            },
            limit=5,
        )

    assert result["derived_search_terms"] == {
        "structured_gene_identifiers": [],
        "resolved_gene_symbols": [],
        "gene_symbols": [],
        "phrases": ["liver steatosis", "steatosis", "fatty liver"],
    }
    assert "phrase similarity" in result["limitations"][1]
    assert "No CompTox assay candidates matched the derived key-event terms." in result["limitations"][2]


@pytest.mark.asyncio
async def test_search_assays_for_key_event_falls_back_to_measurement_methods() -> None:
    class FailingCompTox:
        def search_assay_catalog(self, *, gene_symbols=None, phrases=None, preferred_taxa=None, limit=25):
            raise CompToxError("503 Service Unavailable")

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=FailingCompTox())
        result = await adapter.search_assays_for_key_event(
            {
                "id": "KE:239",
                "title": "Activation, Pregnane-X receptor, NR1I2",
                "short_name": "PXR activation",
                "description": "Pregnane X receptor activation event.",
                "measurement_methods": [
                    "The following ToxCast assays measure PXR activation: ATG_PXRE_CIS; TOX21_PXR_agonist; NVS_NR_hPXR."
                ],
            },
            limit=5,
        )

    assert "measurement-method text" in result["limitations"][1]
    assert result["results"] == [
        {
            "aeid": None,
            "assay_name": "ATG_PXRE_CIS",
            "assay_component_endpoint_name": "ATG_PXRE_CIS",
            "assay_component_endpoint_desc": "Recovered from AOP-Wiki key event measurement methods.",
            "assay_function_type": None,
            "target_family": None,
            "target_family_sub": None,
            "target_type": None,
            "gene_symbols": ["NR1I2", "PXR"],
            "taxon_name": None,
            "applicability_match": "unknown",
            "matched_taxa": [],
            "match_score": 40,
            "match_basis": ["key_event_measurement_methods"],
            "matched_terms": ["ATG_PXRE_CIS"],
            "multi_conc_assay_chemical_count_active": None,
            "multi_conc_assay_chemical_count_total": None,
            "single_conc_assay_chemical_count_active": None,
            "single_conc_assay_chemical_count_total": None,
            "source": "aop_wiki_measurement_methods",
        },
        {
            "aeid": None,
            "assay_name": "TOX21_PXR_agonist",
            "assay_component_endpoint_name": "TOX21_PXR_agonist",
            "assay_component_endpoint_desc": "Recovered from AOP-Wiki key event measurement methods.",
            "assay_function_type": None,
            "target_family": None,
            "target_family_sub": None,
            "target_type": None,
            "gene_symbols": ["NR1I2", "PXR"],
            "taxon_name": None,
            "applicability_match": "unknown",
            "matched_taxa": [],
            "match_score": 40,
            "match_basis": ["key_event_measurement_methods"],
            "matched_terms": ["TOX21_PXR_agonist"],
            "multi_conc_assay_chemical_count_active": None,
            "multi_conc_assay_chemical_count_total": None,
            "single_conc_assay_chemical_count_active": None,
            "single_conc_assay_chemical_count_total": None,
            "source": "aop_wiki_measurement_methods",
        },
        {
            "aeid": None,
            "assay_name": "NVS_NR_hPXR",
            "assay_component_endpoint_name": "NVS_NR_hPXR",
            "assay_component_endpoint_desc": "Recovered from AOP-Wiki key event measurement methods.",
            "assay_function_type": None,
            "target_family": None,
            "target_family_sub": None,
            "target_type": None,
            "gene_symbols": ["NR1I2", "PXR"],
            "taxon_name": None,
            "applicability_match": "unknown",
            "matched_taxa": [],
            "match_score": 40,
            "match_basis": ["key_event_measurement_methods"],
            "matched_terms": ["NVS_NR_hPXR"],
            "multi_conc_assay_chemical_count_active": None,
            "multi_conc_assay_chemical_count_total": None,
            "single_conc_assay_chemical_count_active": None,
            "single_conc_assay_chemical_count_total": None,
            "source": "aop_wiki_measurement_methods",
        },
    ]


@pytest.mark.asyncio
async def test_search_assays_for_key_event_uses_measurement_methods_when_comptox_has_no_matches() -> None:
    class EmptyCompTox:
        def search_assay_catalog(self, *, gene_symbols=None, phrases=None, preferred_taxa=None, limit=25):
            return []

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=EmptyCompTox())
        result = await adapter.search_assays_for_key_event(
            {
                "id": "KE:239",
                "title": "Activation, Pregnane-X receptor, NR1I2",
                "short_name": "PXR activation",
                "description": "Pregnane X receptor activation event.",
                "measurement_methods": [
                    "Reported by ATG_PXRE_CIS and TOX21_PXR_agonist in ToxCast."
                ],
            },
            limit=5,
        )

    assert "measurement-method text was used as a fallback" in result["limitations"][1]
    assert [row["assay_name"] for row in result["results"]] == [
        "ATG_PXRE_CIS",
        "TOX21_PXR_agonist",
    ]


@pytest.mark.asyncio
async def test_search_assays_for_key_event_expands_aliases_and_taxa() -> None:
    class AliasCompTox:
        def search_assay_catalog(self, *, gene_symbols=None, phrases=None, preferred_taxa=None, limit=25):
            assert gene_symbols == ["FXR", "NR1H4"]
            assert phrases == ["farnesoid x receptor"]
            assert preferred_taxa == ["human", "homo sapiens", "mouse", "mus musculus"]
            return []

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=AliasCompTox())
        result = await adapter.search_assays_for_key_event(
            {
                "id": "KE:1419",
                "title": "Reduced, FXR activity",
                "short_name": None,
                "description": None,
                "taxonomic_applicability": ["NCBITaxon:9606", "NCBITaxon:10090"],
            },
            limit=5,
        )

    assert result["derived_search_terms"] == {
        "structured_gene_identifiers": [],
        "resolved_gene_symbols": [],
        "gene_symbols": ["FXR", "NR1H4"],
        "phrases": ["farnesoid x receptor"],
    }


@pytest.mark.asyncio
async def test_search_assays_for_key_event_merges_resolved_hgnc_symbols_with_heuristics() -> None:
    class StubHgnc:
        def resolve_symbol(self, identifier: str) -> str | None:
            return {
                "HGNC:7968": "NR1I2",
                "HGNC:9999": "ABCB11",
            }.get(identifier)

    class KeyEventSearchCompTox:
        def search_assay_catalog(self, *, gene_symbols=None, phrases=None, preferred_taxa=None, limit=25):
            assert gene_symbols == ["NR1I2", "ABCB11", "PXR"]
            assert phrases == ["pregnane x receptor"]
            return []

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(
            client,
            comptox_client=KeyEventSearchCompTox(),
            hgnc_client=StubHgnc(),
        )
        result = await adapter.search_assays_for_key_event(
            {
                "id": "KE:239",
                "title": "Activation, Pregnane-X receptor",
                "short_name": "PXR activation",
                "description": "Pregnane X receptor activation event.",
                "gene_identifiers": ["HGNC:7968", "HGNC:9999"],
            },
            limit=5,
        )

    assert result["derived_search_terms"] == {
        "structured_gene_identifiers": ["HGNC:7968", "HGNC:9999"],
        "resolved_gene_symbols": ["NR1I2", "ABCB11"],
        "gene_symbols": ["NR1I2", "ABCB11", "PXR"],
        "phrases": ["pregnane x receptor"],
    }


@pytest.mark.asyncio
async def test_search_assays_for_key_event_falls_back_when_hgnc_resolution_fails() -> None:
    class FailingHgnc:
        def resolve_symbol(self, identifier: str) -> str | None:
            raise RuntimeError("network unavailable")

    class KeyEventSearchCompTox:
        def search_assay_catalog(self, *, gene_symbols=None, phrases=None, preferred_taxa=None, limit=25):
            assert gene_symbols == ["NR1I2", "PXR"]
            assert phrases == ["pregnane x receptor"]
            return []

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"bindings": []}}))
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(
            client,
            comptox_client=KeyEventSearchCompTox(),
            hgnc_client=FailingHgnc(),
        )
        result = await adapter.search_assays_for_key_event(
            {
                "id": "KE:239",
                "title": "Activation, Pregnane-X receptor, NR1I2",
                "short_name": "PXR activation",
                "description": "Pregnane X receptor activation event.",
                "gene_identifiers": ["HGNC:7968"],
            },
            limit=5,
        )

    assert result["derived_search_terms"]["resolved_gene_symbols"] == []
    assert any("HGNC gene-symbol resolution was unavailable" in item for item in result["limitations"])


@pytest.mark.asyncio
async def test_list_assays_for_aop_prefers_specific_assay_when_support_ties() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "stressor": {"value": "https://identifiers.org/aop.stressor/771"},
                            "stressorLabel": {"value": "Perfluorooctanesulfonic acid"},
                            "chemicalEntity": {"value": "https://identifiers.org/cas/1763-23-1"},
                        }
                    ]
                }
            },
        )

    class SpecificityCompTox(StubCompTox):
        def bioactivity_data_by_dtxsid(self, dtxsid: str):
            return [
                {"aeid": 2309, "hitc": 0.96, "coff": 20.0},
                {"aeid": 2310, "hitc": 0.98, "coff": 18.0},
            ]

        def assay_by_aeid(self, aeid: int):
            assays = {
                2309: {
                    "assayName": "Specific assay",
                    "assayComponentEndpointName": "Specific assay",
                    "assayComponentEndpointDesc": "Specific endpoint",
                    "assayFunctionType": "enzymatic activity",
                    "intendedTargetFamily": "family",
                    "intendedTargetFamilySub": "sub",
                    "gene": [{"geneSymbol": "DIO1"}],
                    "multiConcActives": "20/1000(2.00%)",
                },
                2310: {
                    "assayName": "Promiscuous assay",
                    "assayComponentEndpointName": "Promiscuous assay",
                    "assayComponentEndpointDesc": "Promiscuous endpoint",
                    "assayFunctionType": "enzymatic activity",
                    "intendedTargetFamily": "family",
                    "intendedTargetFamilySub": "sub",
                    "gene": [{"geneSymbol": "DIO1"}],
                    "multiConcActives": "700/1000(70.00%)",
                },
            }
            return assays[aeid]

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPDBAdapter(client, comptox_client=SpecificityCompTox())
        records = await adapter.list_assays_for_aop("AOP:529", limit=10, min_hitcall=0.9)

    assert [record["aeid"] for record in records[:2]] == [2309, 2310]
    assert records[0]["specificity_score"] > records[1]["specificity_score"]


def test_derive_key_event_search_terms_prefers_title_scope_over_description_noise() -> None:
    terms = _derive_key_event_search_terms(
        {
            "title": "Accumulation, Triglyceride",
            "short_name": None,
            "description": (
                "Triglyceride accumulation may be modulated by PXR, FXR, LXR, CAR, and AHR signaling."
            ),
        }
    )

    assert terms == {
        "gene_symbols": [],
        "phrases": ["triglyceride", "steatosis"],
    }


def test_derive_key_event_search_terms_filters_generic_measurement_words() -> None:
    terms = _derive_key_event_search_terms(
        {
            "title": "Reduced, INSIG1 protein",
            "short_name": None,
            "description": "INSIG1 protein abundance is reduced in hepatocytes.",
        }
    )

    assert terms == {
        "gene_symbols": ["INSIG1"],
        "phrases": [],
    }


def test_derive_key_event_search_terms_adds_alias_for_hyphenated_receptor_name() -> None:
    terms = _derive_key_event_search_terms(
        {
            "title": "Activation, Pregnane-X receptor, NR1l2",
            "short_name": None,
            "description": None,
        }
    )

    assert terms == {
        "gene_symbols": ["NR1I2", "PXR"],
        "phrases": ["pregnane x receptor"],
    }


def test_derive_key_event_search_terms_drops_acronym_phrase_when_symbol_present() -> None:
    terms = _derive_key_event_search_terms(
        {
            "title": "Activation, AhR",
            "short_name": None,
            "description": None,
        }
    )

    assert terms == {
        "gene_symbols": ["AHR"],
        "phrases": ["aryl hydrocarbon receptor"],
    }


def test_derive_key_event_search_terms_expands_fatty_liver_synonyms() -> None:
    terms = _derive_key_event_search_terms(
        {
            "title": "Increase, Fatty liver",
            "short_name": None,
            "description": None,
        }
    )

    assert terms == {
        "gene_symbols": [],
        "phrases": ["fatty liver", "steatosis", "liver steatosis"],
    }
