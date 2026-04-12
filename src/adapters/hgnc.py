"""HGNC REST client for resolving HGNC identifiers to gene symbols."""

from __future__ import annotations

from typing import Any

import httpx


class HgncError(Exception):
    """Base exception for HGNC client failures."""


class HgncClient:
    def __init__(
        self,
        base_url: str = "https://rest.genenames.org/",
        *,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._symbol_cache: dict[str, str | None] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HgncClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def resolve_symbol(self, identifier: str) -> str | None:
        normalized_identifier = self._normalize_identifier(identifier)
        if normalized_identifier is None:
            return None
        if normalized_identifier in self._symbol_cache:
            return self._symbol_cache[normalized_identifier]

        response = self._client.get(
            f"fetch/hgnc_id/{normalized_identifier}",
            headers={"Accept": "application/json"},
        )
        payload = self._handle_response(response)
        docs = payload.get("response", {}).get("docs", [])
        symbol = None
        if isinstance(docs, list) and docs:
            first = docs[0]
            if isinstance(first, dict):
                raw_symbol = first.get("symbol")
                if isinstance(raw_symbol, str) and raw_symbol.strip():
                    symbol = raw_symbol.strip().upper()
        self._symbol_cache[normalized_identifier] = symbol
        return symbol

    @staticmethod
    def _normalize_identifier(identifier: str | None) -> str | None:
        if not identifier:
            return None
        normalized = identifier.strip().upper()
        if not normalized.startswith("HGNC:"):
            return None
        suffix = normalized.split(":", 1)[1]
        if not suffix.isdigit():
            return None
        return f"HGNC:{suffix}"

    @staticmethod
    def _handle_response(response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 404:
            return {}
        if response.status_code >= 400:
            raise HgncError(f"HGNC request failed: {response.status_code} {response.text}")
        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise HgncError("HGNC response was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise HgncError("HGNC response was not a JSON object")
        return payload
