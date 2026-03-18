from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.adapters import CompToxClient, CompToxError, extract_identifiers


class MockTransport(httpx.BaseTransport):
    def __init__(self, responses: dict[str, httpx.Response]) -> None:
        self.responses = responses

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.responses.get(str(request.url))
        if response is None:
            raise AssertionError(f"Unexpected URL {request.url}")
        return response


def make_response(url: str, status: int, json_data: Any | None = None, text: str | None = None) -> tuple[str, httpx.Response]:
    return (
        url,
        httpx.Response(status, json=json_data) if json_data is not None else httpx.Response(status, text=text or ""),
    )


def test_comp_tox_client_search_returns_results() -> None:
    responses = dict([
        make_response(
            "https://comptox.epa.gov/dashboard/api/search/chemicals?search=aspirin",
            200,
            json_data={"results": [{"preferredName": "Aspirin"}]},
        )
    ])
    transport = MockTransport(responses)
    with CompToxClient(transport=transport) as client:
        results = client.search("aspirin")

    assert results == [{"preferredName": "Aspirin"}]


def test_comp_tox_client_search_equal_uses_ctx_api() -> None:
    responses = dict([
        make_response(
            "https://comptox.epa.gov/ctx-api/chemical/search/equal/1763-23-1",
            200,
            json_data=[{"dtxsid": "DTXSID3031864"}],
        )
    ])
    transport = MockTransport(responses)
    with CompToxClient(transport=transport, api_key="test-key") as client:
        results = client.search_equal("1763-23-1")

    assert results == [{"dtxsid": "DTXSID3031864"}]


def test_comp_tox_client_bioactivity_data_by_dtxsid_returns_rows() -> None:
    responses = dict([
        make_response(
            "https://comptox.epa.gov/ctx-api/bioactivity/data/search/by-dtxsid/DTXSID3031864",
            200,
            json_data=[{"aeid": 2309, "hitc": 0.95}],
        )
    ])
    transport = MockTransport(responses)
    with CompToxClient(transport=transport, api_key="test-key") as client:
        rows = client.bioactivity_data_by_dtxsid("DTXSID3031864")

    assert rows == [{"aeid": 2309, "hitc": 0.95}]


def test_comp_tox_client_assay_by_aeid_returns_first_annotation() -> None:
    responses = dict([
        make_response(
            "https://comptox.epa.gov/ctx-api/bioactivity/assay/search/by-aeid/2309",
            200,
            json_data=[{"aeid": 2309, "assayName": "CCTE_GLTED_hDIO1"}],
        )
    ])
    transport = MockTransport(responses)
    with CompToxClient(transport=transport, api_key="test-key") as client:
        assay = client.assay_by_aeid(2309)

    assert assay == {"aeid": 2309, "assayName": "CCTE_GLTED_hDIO1"}


def test_comp_tox_client_assays_by_gene_returns_rows() -> None:
    responses = dict([
        make_response(
            "https://comptox.epa.gov/ctx-api/bioactivity/assay/search/by-gene/NR1I2",
            200,
            json_data=[{"aeid": 103, "geneSymbol": "NR1I2"}],
        )
    ])
    transport = MockTransport(responses)
    with CompToxClient(transport=transport, api_key="test-key") as client:
        assays = client.assays_by_gene("NR1I2")

    assert assays == [{"aeid": 103, "geneSymbol": "NR1I2"}]


def test_comp_tox_client_all_assays_returns_rows() -> None:
    responses = dict([
        make_response(
            "https://comptox.epa.gov/ctx-api/bioactivity/assay/",
            200,
            json_data=[{"aeid": 916, "assayName": "LTEA_HepaRG"}],
        )
    ])
    transport = MockTransport(responses)
    with CompToxClient(transport=transport, api_key="test-key") as client:
        assays = client.all_assays()

    assert assays == [{"aeid": 916, "assayName": "LTEA_HepaRG"}]


def test_comp_tox_client_handles_not_found() -> None:
    responses = dict([
        make_response(
            "https://comptox.epa.gov/dashboard/api/chemical/info/UNKNOWN",
            404,
            json_data=None,
        )
    ])
    transport = MockTransport(responses)
    with CompToxClient(transport=transport) as client:
        assert client.chemical_by_inchikey("UNKNOWN") is None


def test_comp_tox_client_raises_on_error() -> None:
    responses = dict([
        make_response(
            "https://comptox.epa.gov/dashboard/api/chemical/info/ERR",
            500,
            text="server error",
        )
    ])
    transport = MockTransport(responses)
    with CompToxClient(transport=transport) as client:
        with pytest.raises(CompToxError):
            client.chemical_by_inchikey("ERR")


def test_extract_identifiers_returns_expected_fields() -> None:
    payload = {
        "preferredName": "Aspirin",
        "inchikey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        "casrn": "50-78-2",
        "dsstoxSubstanceId": "DTXSID3020001",
        "dsstoxCompoundId": "DTXCID1010001",
    }

    result = extract_identifiers(payload)

    assert result["preferred_name"] == "Aspirin"
    assert result["casrn"] == "50-78-2"


def test_comp_tox_client_search_assay_catalog_ranks_gene_and_phrase_matches(monkeypatch) -> None:
    catalog_items = [
        {
            "aeid": 103,
            "assayName": "ATG_PXRE_CIS",
            "assayComponentEndpointName": "ATG_PXRE_CIS",
            "assayComponentEndpointDesc": "Pregnane X receptor reporter assay",
            "taxonName": "human",
            "multi_conc_assay_chemical_count_active": 600,
            "multi_conc_assay_chemical_count_total": 1000,
            "single_conc_assay_chemical_count_active": 0,
            "single_conc_assay_chemical_count_total": 0,
            "genes": [{"geneSymbol": "NR1I2", "geneName": "pregnane X receptor"}],
        },
        {
            "aeid": 2309,
            "assayName": "CCTE_GLTED_hDIO1",
            "assayComponentEndpointName": "CCTE_GLTED_hDIO1",
            "assayComponentEndpointDesc": "DIO1 activity assay",
            "taxonName": "human",
            "multi_conc_assay_chemical_count_active": 50,
            "multi_conc_assay_chemical_count_total": 400,
            "single_conc_assay_chemical_count_active": 0,
            "single_conc_assay_chemical_count_total": 0,
            "genes": [{"geneSymbol": "DIO1", "geneName": "iodothyronine deiodinase 1"}],
        },
    ]

    with CompToxClient() as client:
        monkeypatch.setattr(client, "assays_by_gene", lambda symbol: [])
        monkeypatch.setattr(client, "all_assays", lambda: (_ for _ in ()).throw(CompToxError("full api unavailable")))
        monkeypatch.setattr(client, "assay_catalog_items", lambda: catalog_items)
        monkeypatch.setattr(
            client,
            "assay_by_aeid",
            lambda aeid: {
                103: {
                    "assayName": "ATG_PXRE_CIS",
                    "assayComponentEndpointName": "ATG_PXRE_CIS",
                    "assayComponentEndpointDesc": "Pregnane X receptor reporter assay",
                    "assayFunctionType": "reporter gene",
                    "intendedTargetFamily": "nuclear receptor",
                    "intendedTargetFamilySub": "PXR",
                    "intendedTargetType": "protein",
                    "gene": [{"geneSymbol": "NR1I2"}],
                }
            }.get(aeid),
        )

        results = client.search_assay_catalog(
            gene_symbols=["NR1I2", "PXR"],
            phrases=["pregnane x receptor"],
            preferred_taxa=["human"],
            limit=5,
        )

    assert [row["aeid"] for row in results] == [103]
    assert results[0]["applicability_match"] == "match"
    assert results[0]["matched_taxa"] == ["human"]
    assert "gene_symbol_exact" in results[0]["match_basis"]
    assert "pregnane x receptor" in results[0]["matched_terms"]
    assert results[0]["target_family"] == "nuclear receptor"


def test_comp_tox_client_search_assay_catalog_uses_full_api_for_phrase_only(monkeypatch) -> None:
    with CompToxClient() as client:
        monkeypatch.setattr(client, "all_assays", lambda: [
            {
                "aeid": 916,
                "assayName": "LTEA_HepaRG",
                "assayComponentName": "LTEA_HepaRG_steatosis",
                "assayComponentEndpointName": "LTEA_HepaRG_steatosis",
                "assayComponentEndpointDesc": "Human HepaRG transcriptomic assay panel related to steatosis responses.",
                "assayDesc": "A HepaRG liver model for steatosis-associated response profiling.",
                "organism": "human",
                "gene": [{"geneSymbol": "LIPC", "geneName": "lipase C"}],
            }
        ])
        monkeypatch.setattr(
            client,
            "assay_catalog_items",
            lambda: (_ for _ in ()).throw(AssertionError("catalog fallback should not be used")),
        )

        results = client.search_assay_catalog(
            phrases=["liver steatosis"],
            preferred_taxa=["human"],
            limit=5,
        )

    assert [row["aeid"] for row in results] == [916]
    assert results[0]["source"] == "comptox_assay_api"
    assert results[0]["applicability_match"] == "match"
    assert "steatosis" in results[0]["matched_terms"]
    assert any(basis.startswith("assay_") for basis in results[0]["match_basis"])


def test_comp_tox_client_search_assay_catalog_returns_clean_empty_when_full_api_has_no_phrase_hits(monkeypatch) -> None:
    with CompToxClient() as client:
        monkeypatch.setattr(
            client,
            "all_assays",
            lambda: [
                {
                    "aeid": 1,
                    "assayName": "Example",
                    "assayComponentEndpointName": "Example_endpoint",
                    "assayComponentEndpointDesc": "No relevant phenotype text here.",
                    "organism": "human",
                }
            ],
        )
        monkeypatch.setattr(
            client,
            "assay_catalog_items",
            lambda: (_ for _ in ()).throw(AssertionError("catalog fallback should not be used")),
        )

        results = client.search_assay_catalog(
            phrases=["triglyceride"],
            preferred_taxa=["human"],
            limit=5,
        )

    assert results == []


def test_comp_tox_client_search_assay_catalog_prefers_direct_gene_api(monkeypatch) -> None:
    with CompToxClient() as client:
        monkeypatch.setattr(
            client,
            "assays_by_gene",
            lambda symbol: [
                {
                    "aeid": 103,
                    "geneSymbol": "NR1I2",
                    "assayComponentEndpointName": "ATG_PXRE_CIS",
                    "assayComponentEndpointDesc": "Pregnane X receptor reporter assay",
                    "multiConcActives": "2076/4060(51.13%)",
                    "singleConcActive": "0/310(0.00%)",
                }
            ]
            if symbol == "NR1I2"
            else [],
        )
        monkeypatch.setattr(
            client,
            "assay_by_aeid",
            lambda aeid: {
                "assayName": "ATG_CIS",
                "assayComponentEndpointName": "ATG_PXRE_CIS",
                "assayComponentEndpointDesc": "Pregnane X receptor reporter assay",
                "assayFunctionType": "reporter gene",
                "intendedTargetFamily": "nuclear receptor",
                "intendedTargetFamilySub": "non-steroidal",
                "intendedTargetType": "protein",
                "organism": "human",
                "gene": [{"geneSymbol": "NR1I2", "geneName": "pregnane X receptor"}],
            },
        )
        monkeypatch.setattr(
            client,
            "assay_catalog_items",
            lambda: (_ for _ in ()).throw(AssertionError("catalog fallback should not be used")),
        )
        monkeypatch.setattr(client, "all_assays", lambda: (_ for _ in ()).throw(AssertionError("full api fallback should not be used")))

        results = client.search_assay_catalog(
            gene_symbols=["NR1I2", "PXR"],
            phrases=["pregnane x receptor"],
            preferred_taxa=["human"],
            limit=5,
        )

    assert [row["aeid"] for row in results] == [103]
    assert results[0]["source"] == "comptox_assay_gene_api"
    assert results[0]["assay_name"] == "ATG_CIS"
    assert results[0]["gene_symbols"] == ["NR1I2"]
    assert results[0]["applicability_match"] == "match"
    assert results[0]["matched_taxa"] == ["human"]
    assert results[0]["multi_conc_assay_chemical_count_active"] == 2076
    assert results[0]["multi_conc_assay_chemical_count_total"] == 4060
    assert results[0]["single_conc_assay_chemical_count_active"] == 0
    assert results[0]["single_conc_assay_chemical_count_total"] == 310
    assert results[0]["match_score"] >= 300
    assert "ctx_gene_search_exact" in results[0]["match_basis"]
    assert "gene_name_exact" in results[0]["match_basis"]
    assert "taxonomic_applicability_match" in results[0]["match_basis"]
    assert "NR1I2" in results[0]["matched_terms"]
    assert "pregnane x receptor" in results[0]["matched_terms"]


def test_comp_tox_client_search_assay_catalog_falls_back_to_catalog_metadata(monkeypatch) -> None:
    catalog_items = [
        {
            "aeid": 103,
            "assayName": "ATG_PXRE_CIS",
            "assayComponentEndpointName": "ATG_PXRE_CIS",
            "assayComponentEndpointDesc": "Pregnane X receptor reporter assay",
            "taxonName": "human",
            "multi_conc_assay_chemical_count_active": 600,
            "multi_conc_assay_chemical_count_total": 1000,
            "single_conc_assay_chemical_count_active": 0,
            "single_conc_assay_chemical_count_total": 0,
            "genes": [{"geneSymbol": "NR1I2", "geneName": "pregnane X receptor"}],
        }
    ]

    with CompToxClient() as client:
        monkeypatch.setattr(client, "assays_by_gene", lambda symbol: [])
        monkeypatch.setattr(client, "all_assays", lambda: (_ for _ in ()).throw(CompToxError("full api unavailable")))
        monkeypatch.setattr(client, "assay_catalog_items", lambda: catalog_items)

        def fail_assay_lookup(aeid: int) -> dict[str, Any] | None:
            raise CompToxError(f"lookup failed for {aeid}")

        monkeypatch.setattr(client, "assay_by_aeid", fail_assay_lookup)
        results = client.search_assay_catalog(gene_symbols=["NR1I2"], limit=5)

    assert results == [
        {
            "aeid": 103,
            "assay_name": "ATG_PXRE_CIS",
            "assay_component_endpoint_name": "ATG_PXRE_CIS",
            "assay_component_endpoint_desc": "Pregnane X receptor reporter assay",
            "assay_function_type": None,
            "target_family": None,
            "target_family_sub": None,
            "target_type": None,
            "gene_symbols": ["NR1I2"],
            "taxon_name": "human",
            "applicability_match": "unknown",
            "matched_taxa": [],
            "match_score": 122,
            "match_basis": ["gene_symbol_exact"],
            "matched_terms": ["NR1I2"],
            "multi_conc_assay_chemical_count_active": 600,
            "multi_conc_assay_chemical_count_total": 1000,
            "single_conc_assay_chemical_count_active": 0,
            "single_conc_assay_chemical_count_total": 0,
            "source": "comptox_assay_catalog",
        }
    ]


def test_comp_tox_client_search_assay_catalog_prefers_matching_taxa(monkeypatch) -> None:
    catalog_items = [
        {
            "aeid": 10,
            "assayName": "FXR_human",
            "assayComponentEndpointName": "FXR_human",
            "assayComponentEndpointDesc": "Farnesoid X receptor human assay",
            "taxonName": "human",
            "multi_conc_assay_chemical_count_active": 10,
            "multi_conc_assay_chemical_count_total": 100,
            "single_conc_assay_chemical_count_active": 0,
            "single_conc_assay_chemical_count_total": 0,
            "genes": [{"geneSymbol": "NR1H4", "geneName": "farnesoid X receptor"}],
        },
        {
            "aeid": 11,
            "assayName": "FXR_rat",
            "assayComponentEndpointName": "FXR_rat",
            "assayComponentEndpointDesc": "Farnesoid X receptor rat assay",
            "taxonName": "rat",
            "multi_conc_assay_chemical_count_active": 10,
            "multi_conc_assay_chemical_count_total": 100,
            "single_conc_assay_chemical_count_active": 0,
            "single_conc_assay_chemical_count_total": 0,
            "genes": [{"geneSymbol": "NR1H4", "geneName": "farnesoid X receptor"}],
        },
    ]

    with CompToxClient() as client:
        monkeypatch.setattr(client, "assays_by_gene", lambda symbol: [])
        monkeypatch.setattr(client, "all_assays", lambda: (_ for _ in ()).throw(CompToxError("full api unavailable")))
        monkeypatch.setattr(client, "assay_catalog_items", lambda: catalog_items)
        monkeypatch.setattr(client, "assay_by_aeid", lambda aeid: None)
        results = client.search_assay_catalog(
            gene_symbols=["NR1H4"],
            phrases=["farnesoid x receptor"],
            preferred_taxa=["human"],
            limit=5,
        )

    assert [row["aeid"] for row in results] == [10, 11]
    assert results[0]["applicability_match"] == "match"
    assert results[1]["applicability_match"] == "mismatch"
