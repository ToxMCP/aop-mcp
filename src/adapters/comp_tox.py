"""CompTox Dashboard client for chemical metadata mapping."""

from __future__ import annotations

from typing import Any

import httpx


class CompToxError(Exception):
    """Base exception for CompTox client."""


class CompToxClient:
    def __init__(
        self,
        base_url: str = "https://comptox.epa.gov/dashboard/api/",
        bioactivity_url: str = "https://comptox.epa.gov/ctx-api/",
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._bio_client = httpx.Client(base_url=bioactivity_url, timeout=timeout, transport=transport)
        self._api_key = api_key

    def close(self) -> None:
        self._client.close()
        self._bio_client.close()

    def __enter__(self) -> "CompToxClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
            # ctx-api expects lowercase header usually, but requests is case insensitive. 
            # however, let's be safe for bioactivity which might be strict.
            headers["x-api-key"] = self._api_key
        return headers

    def chemical_by_inchikey(self, inchikey: str) -> dict[str, Any] | None:
        response = self._client.get(f"chemical/info/{inchikey}", headers=self._headers())
        return self._handle_response(response)

    def chemical_by_cas(self, cas: str) -> dict[str, Any] | None:
        response = self._client.get(f"chemical/info/{cas}", headers=self._headers())
        return self._handle_response(response)

    def search(self, name: str) -> list[dict[str, Any]]:
        response = self._client.get("search/chemicals", params={"search": name}, headers=self._headers())
        payload = self._handle_response(response)
        if payload is None:
            return []
        results = payload.get("results", [])
        return results if isinstance(results, list) else []

    def get_chemicals_in_assay(self, aeid: str) -> list[dict[str, Any]]:
        """Fetch chemicals active in a specific assay (by AEID) from Bioactivity API."""
        # Endpoint: bioactivity/assay/chemicals/search/by-aeid/{aeid}
        # Note: We use _bio_client which points to ctx-api
        response = self._bio_client.get(f"bioactivity/assay/chemicals/search/by-aeid/{aeid}", headers=self._headers())
        # Bioactivity API returns a list of objects directly, or empty list
        payload = self._handle_response(response)
        if payload is None:
            return []
        return payload if isinstance(payload, list) else []

    @staticmethod
    def _handle_response(response: httpx.Response) -> dict[str, Any] | list[Any] | None:
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise CompToxError(f"CompTox request failed: {response.status_code} {response.text}")
        data = response.json()
        return data


def extract_identifiers(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "preferred_name": record.get("preferredName"),
        "inchikey": record.get("inchikey"),
        "casrn": record.get("casrn"),
        "dsstox_substance_id": record.get("dsstoxSubstanceId"),
        "dsstox_compound_id": record.get("dsstoxCompoundId"),
    }

