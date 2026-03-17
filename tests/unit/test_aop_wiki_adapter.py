from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.adapters import AOPWikiAdapter, SparqlClient


def make_client(handler: httpx.MockTransport) -> SparqlClient:
    return SparqlClient(["https://sparql.example/aopwiki"], transport=handler)


@pytest.mark.asyncio
async def test_search_aops_filters_and_normalizes_results() -> None:
    captured_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_queries.append(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "aop": {"value": "http://aopwiki.org/aops/123"},
                            "title": {"value": "Estrogen leads to reproductive failure"},
                            "shortName": {"value": "AOP123"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        results = await adapter.search_aops(text="Estrogen", limit=5)

    assert len(results) == 1
    assert results[0]["id"] == "AOP:123"
    assert results[0]["title"] == "Estrogen leads to reproductive failure"
    assert "LIMIT 5" in captured_queries[0]
    assert 'OPTIONAL { ?aop dc:description ?abstract }' in captured_queries[0]
    assert 'FILTER (?score > 0 && ?matchCount >= 1)' in captured_queries[0]
    assert 'ORDER BY DESC(?surfaceMatchCount) DESC(?score) LCASE(?title)' in captured_queries[0]
    assert 'CONTAINS(LCASE(COALESCE(?title, "")), "estrogen")' in captured_queries[0]
    assert 'CONTAINS(LCASE(COALESCE(?abstract, "")), "estrogen")' in captured_queries[0]


@pytest.mark.asyncio
async def test_search_aops_expands_common_liver_synonyms() -> None:
    captured_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_queries.append(request.content.decode("utf-8"))
        return httpx.Response(200, json={"results": {"bindings": []}})

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        await adapter.search_aops(text="liver steatosis", limit=5)

    assert '"hepatic"' in captured_queries[0]
    assert '"fatty liver"' in captured_queries[0]


@pytest.mark.asyncio
async def test_get_aop_returns_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        assert "<https://identifiers.org/aop/42> dc:title ?title ." in query
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "title": {"value": "Oxidative stress"},
                            "shortName": {"value": "AOP42"},
                            "status": {"value": "OECD:Draft"},
                            "abstract": {"value": "Mechanistic description"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        record = await adapter.get_aop("AOP:42")

    assert record["id"] == "AOP:42"
    assert record["short_name"] == "AOP42"
    assert record["status"] == "OECD:Draft"
    assert record["abstract"] == "Mechanistic description"


@pytest.mark.asyncio
async def test_get_aop_assessment_returns_evidence_mie_and_ao() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        assert "BIND(<https://identifiers.org/aop/232> AS ?aop)" in query
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "title": {"value": "NFE2/Nrf2 repression to steatosis"},
                            "shortName": {"value": "AOP232"},
                            "abstract": {"value": "Steatosis is a regulatory endpoint."},
                            "evidence": {"value": "Overall Moderate support."},
                            "created": {"value": "2024-01-01T00:00:00"},
                            "modified": {"value": "2025-01-02T00:00:00"},
                            "mie": {"value": "https://identifiers.org/aop.events/1417"},
                            "mieTitle": {"value": "NFE2/Nrf2 repression"},
                            "ao": {"value": "https://identifiers.org/aop.events/459"},
                            "aoTitle": {"value": "Increase, Liver steatosis"},
                        },
                        {
                            "mie": {"value": "https://identifiers.org/aop.events/1417"},
                            "ao": {"value": "https://identifiers.org/aop.events/459"},
                        },
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        record = await adapter.get_aop_assessment("AOP:232")

    assert record["id"] == "AOP:232"
    assert record["evidence_summary"] == "Overall Moderate support."
    assert record["molecular_initiating_events"] == [
        {
            "id": "KE:1417",
            "iri": "https://identifiers.org/aop.events/1417",
            "title": "NFE2/Nrf2 repression",
        }
    ]
    assert record["adverse_outcomes"] == [
        {
            "id": "KE:459",
            "iri": "https://identifiers.org/aop.events/459",
            "title": "Increase, Liver steatosis",
        }
    ]


@pytest.mark.asyncio
async def test_list_key_events_normalizes_ke_identifiers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "<https://identifiers.org/aop/99> aopo:has_key_event ?ke ." in request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "ke": {"value": "http://aopwiki.org/events/567"},
                            "label": {"value": "Mitochondrial dysfunction"},
                            "eventType": {"value": "Cellular"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        key_events = await adapter.list_key_events("AOP:99")

    assert key_events == [
        {
            "id": "KE:567",
            "iri": "http://aopwiki.org/events/567",
            "title": "Mitochondrial dysfunction",
            "event_type": "Cellular",
        }
    ]


@pytest.mark.asyncio
async def test_list_kers_returns_upstream_and_downstream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "ker": {"value": "http://aopwiki.org/relationships/888"},
                            "upstream": {"value": "http://aopwiki.org/events/100"},
                            "downstream": {"value": "http://aopwiki.org/events/200"},
                            "plausibility": {"value": "strong"},
                            "status": {"value": "KC-curated"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        relationships = await adapter.list_kers("AOP:500")

    assert relationships == [
        {
            "id": "KER:888",
            "iri": "http://aopwiki.org/relationships/888",
            "upstream": {"id": "KE:100", "iri": "http://aopwiki.org/events/100"},
            "downstream": {"id": "KE:200", "iri": "http://aopwiki.org/events/200"},
            "plausibility": "strong",
            "status": "KC-curated",
        }
    ]


@pytest.mark.asyncio
async def test_get_key_event_aggregates_oecd_style_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        assert "BIND(<https://identifiers.org/aop.events/239> AS ?ke)" in query
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "title": {"value": "Activation, Pregnane-X receptor, NR1I2"},
                            "shortName": {"value": "PXR activation"},
                            "description": {"value": "Pregnane X receptor activation event."},
                            "level": {"value": "Molecular"},
                            "lifeStage": {"value": "All life stages"},
                            "direction": {"value": "increased"},
                            "sex": {"value": "Unspecific"},
                            "measurement": {"value": "Measured by transcriptomics."},
                            "gene": {"value": "https://identifiers.org/hgnc/7968"},
                            "protein": {"value": "http://purl.obolibrary.org/obo/PR_000011397"},
                            "biologicalProcess": {"value": "http://purl.obolibrary.org/obo/GO_0023052"},
                            "taxon": {"value": "http://purl.bioontology.org/ontology/NCBITAXON/9606"},
                            "cellType": {"value": "http://purl.obolibrary.org/obo/CL_0000255"},
                            "aop": {"value": "https://identifiers.org/aop/517"},
                            "aopTitle": {"value": "PXR activation leads to liver steatosis"},
                        },
                        {
                            "measurement": {"value": "Measured by reporter assay."},
                            "gene": {"value": "https://identifiers.org/hgnc/1663"},
                            "organ": {"value": "liver"},
                            "taxon": {"value": "WikiUser_17"},
                            "aop": {"value": "https://identifiers.org/aop/545"},
                            "aopTitle": {"value": "PXR activation to decreased INSIG1"},
                        },
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        record = await adapter.get_key_event("KE:239")

    assert record["id"] == "KE:239"
    assert record["title"] == "Activation, Pregnane-X receptor, NR1I2"
    assert record["measurement_methods"] == ["Measured by transcriptomics.", "Measured by reporter assay."]
    assert record["gene_identifiers"] == ["HGNC:7968", "HGNC:1663"]
    assert record["taxonomic_applicability"] == ["NCBITaxon:9606"]
    assert record["shared_aop_count"] == 2


@pytest.mark.asyncio
async def test_get_ker_returns_plausibility_evidence_and_quantitative_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        assert "BIND(<https://identifiers.org/aop.relationships/3365> AS ?ker)" in query
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "upstream": {"value": "https://identifiers.org/aop.events/239"},
                            "downstream": {"value": "https://identifiers.org/aop.events/2268"},
                            "upstreamTitle": {"value": "Activation, Pregnane-X receptor, NR1I2"},
                            "downstreamTitle": {"value": "Decreased, INSIG1 activity"},
                            "description": {"value": "Persistent activation of PXR decreases INSIG1 activity."},
                            "plausibility": {"value": "Strong mechanistic rationale."},
                            "empiricalSupport": {"value": "Temporal and dose concordance observed."},
                            "quantitativeUnderstanding": {"value": "Quantitative support is moderate."},
                            "gene": {"value": "https://identifiers.org/hgnc/7968"},
                            "created": {"value": "2024-10-22T13:49:17"},
                            "modified": {"value": "2025-02-10T15:57:38"},
                            "aop": {"value": "https://identifiers.org/aop/517"},
                            "aopTitle": {"value": "PXR activation leads to liver steatosis"},
                        },
                        {
                            "aop": {"value": "https://identifiers.org/aop/545"},
                            "aopTitle": {"value": "PXR activation to decreased INSIG1"},
                        },
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        record = await adapter.get_ker("KER:3365")

    assert record["id"] == "KER:3365"
    assert record["title"] == "Activation, Pregnane-X receptor, NR1I2 leads to Decreased, INSIG1 activity"
    assert record["biological_plausibility"] == "Strong mechanistic rationale."
    assert record["empirical_support"] == "Temporal and dose concordance observed."
    assert record["quantitative_understanding"] == "Quantitative support is moderate."
    assert record["shared_aop_count"] == 2


@pytest.mark.asyncio
async def test_get_related_aops_returns_shared_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.content.decode("utf-8")
        assert "<https://identifiers.org/aop/232>" in query
        return httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "relatedAop": {"value": "https://identifiers.org/aop/517"},
                            "title": {"value": "PXR activation leads to liver steatosis"},
                            "sharedKeCount": {"value": "3"},
                            "sharedKerCount": {"value": "1"},
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with make_client(transport) as client:
        adapter = AOPWikiAdapter(client)
        results = await adapter.get_related_aops("AOP:232", limit=10)

    assert results == [
        {
            "id": "AOP:517",
            "iri": "https://identifiers.org/aop/517",
            "title": "PXR activation leads to liver steatosis",
            "shared_key_event_count": 3,
            "shared_ker_count": 1,
            "total_shared_elements": 4,
        }
    ]
