from __future__ import annotations

import httpx
import pytest

from src.adapters import AOPDBAdapter, SparqlClient


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
