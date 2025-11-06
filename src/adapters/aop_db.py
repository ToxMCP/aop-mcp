"""AOP-DB SPARQL adapter for chemical and assay mappings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .fixtures import FixtureNotFoundError, load_fixture
from .sparql_client import SparqlClient, SparqlClientError
from .sparql_client import TemplateCatalog as _TemplateCatalog
from .aop_wiki import _iri_to_curie  # reuse IRI normalization

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "aop_db"


class AOPDBAdapter:
    def __init__(
        self,
        client: SparqlClient,
        cache_ttl_seconds: int = 600,
        *,
        enable_fixture_fallback: bool = True,
    ) -> None:
        self.client = client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._templates = _TemplateCatalog.from_directory(TEMPLATE_DIR)
        self.enable_fixture_fallback = enable_fixture_fallback

    async def map_chemical_to_aops(
        self,
        *,
        inchikey: str | None = None,
        cas: str | None = None,
        name: str | None = None,
    ) -> list[dict[str, Any]]:
        if not any([inchikey, cas, name]):
            raise ValueError("At least one identifier (inchikey, cas, name) must be provided")

        query = self._templates.render(
            "map_chemical_to_aops",
            {
                "inchikey": inchikey or "",
                "cas": cas or "",
                "name": name or "",
            },
        )
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError:
            payload = self._load_fixture("aop_db", "map_chemical_to_aops")
        bindings = payload.get("results", {}).get("bindings", [])
        results: list[dict[str, Any]] = []
        for row in bindings:
            aop = row.get("aop", {})
            stress_id = row.get("stressId", {})
            results.append(
                {
                    "aop": {
                        "id": _iri_to_curie(aop.get("value", "")),
                        "iri": aop.get("value"),
                        "title": row.get("title", {}).get("value"),
                    },
                    "stressor_id": stress_id.get("value"),
                }
            )
        return results

    async def map_assay_to_aops(self, assay_id: str) -> list[dict[str, Any]]:
        if not assay_id:
            raise ValueError("assay_id is required")
        query = self._templates.render("map_assay_to_aops", {"assay_id": assay_id})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError:
            payload = self._load_fixture("aop_db", "map_assay_to_aops")
        bindings = payload.get("results", {}).get("bindings", [])
        results: list[dict[str, Any]] = []
        for row in bindings:
            aop = row.get("aop", {})
            results.append(
                {
                    "aop": {
                        "id": _iri_to_curie(aop.get("value", "")),
                        "iri": aop.get("value"),
                        "title": row.get("title", {}).get("value"),
                    },
                    "assay_id": assay_id,
                }
            )
        return results

    def _load_fixture(self, namespace: str, name: str) -> dict[str, Any]:
        if not self.enable_fixture_fallback:
            raise
        try:
            return load_fixture(namespace, name)
        except FixtureNotFoundError as exc:  # pragma: no cover - defensive fallback
            raise SparqlClientError(str(exc)) from exc
