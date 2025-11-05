from __future__ import annotations

import httpx
import pytest

from src.adapters import AOPDBAdapter, SparqlClient


def make_client(handler: httpx.MockTransport) -> SparqlClient:
    return SparqlClient(["https://sparql.example/aopdb"], transport=handler)


@pytest.mark.asyncio
async def test_map_chemical_to_aops_returns_records() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "VALUES ?identifier" in request.content.decode("utf-8")
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
        records = await adapter.map_chemical_to_aops(inchikey="ABCDEF")

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

