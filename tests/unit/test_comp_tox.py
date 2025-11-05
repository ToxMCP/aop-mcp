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
