from __future__ import annotations

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
            assert phrases == ["liver steatosis"]
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
        "gene_symbols": [],
        "phrases": ["liver steatosis"],
    }
    assert "phrase similarity" in result["limitations"][1]
    assert "No CompTox assay catalog entries matched the derived key-event terms." in result["limitations"][2]


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
        "gene_symbols": ["FXR", "NR1H4"],
        "phrases": ["farnesoid x receptor"],
    }


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
        "phrases": ["triglyceride"],
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
