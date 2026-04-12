from __future__ import annotations

import httpx

from src.adapters.hgnc import HgncClient


class MockTransport(httpx.BaseTransport):
    def __init__(self, responses: dict[str, httpx.Response]) -> None:
        self.responses = responses
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        response = self.responses.get(str(request.url))
        if response is None:
            raise AssertionError(f"Unexpected URL {request.url}")
        return response


def test_hgnc_client_resolves_symbol_and_caches_result() -> None:
    transport = MockTransport(
        {
            "https://rest.genenames.org/fetch/hgnc_id/HGNC:7968": httpx.Response(
                200,
                json={"response": {"docs": [{"symbol": "NR1I2"}]}},
            )
        }
    )

    with HgncClient(transport=transport) as client:
        assert client.resolve_symbol("HGNC:7968") == "NR1I2"
        assert client.resolve_symbol("hgnc:7968") == "NR1I2"

    assert transport.calls == 1


def test_hgnc_client_returns_none_for_missing_or_invalid_identifier() -> None:
    transport = MockTransport(
        {
            "https://rest.genenames.org/fetch/hgnc_id/HGNC:999999": httpx.Response(
                404,
                text="not found",
            )
        }
    )

    with HgncClient(transport=transport) as client:
        assert client.resolve_symbol("HGNC:999999") is None
        assert client.resolve_symbol("ENSEMBL:123") is None
