"""AOP-Wiki SPARQL adapter utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .fixtures import FixtureNotFoundError, load_fixture
from .sparql_client import SparqlClient, SparqlClientError
from .sparql_client import TemplateCatalog as _TemplateCatalog

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "aop_wiki"


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _iri_to_curie(iri: str) -> str:
    if iri.startswith("https://identifiers.org/aop/"):
        return f"AOP:{iri.rsplit('/', 1)[-1]}"
    if iri.startswith("https://identifiers.org/aop.events/"):
        return f"KE:{iri.rsplit('/', 1)[-1]}"
    if iri.startswith("https://identifiers.org/aop.relationships/"):
        return f"KER:{iri.rsplit('/', 1)[-1]}"
    if iri.startswith("http://aopwiki.org/aops/"):
        return f"AOP:{iri.rsplit('/', 1)[-1]}"
    if iri.startswith("http://aopwiki.org/events/"):
        return f"KE:{iri.rsplit('/', 1)[-1]}"
    if iri.startswith("http://aopwiki.org/relationships/"):
        return f"KER:{iri.rsplit('/', 1)[-1]}"
    return iri


def _binding_value(binding: dict[str, Any], key: str) -> str | None:
    value_block = binding.get(key)
    if not value_block:
        return None
    return value_block.get("value")


def _normalize_binding_identifier(binding: dict[str, Any], key: str) -> dict[str, str | None]:
    iri = _binding_value(binding, key)
    if iri is None:
        return {"id": None, "iri": None}
    return {"id": _iri_to_curie(iri), "iri": iri}


@dataclass
class AOPWikiAdapter:
    """Adapter around the AOP-Wiki SPARQL endpoint."""

    client: SparqlClient
    cache_ttl_seconds: int = 300
    enable_fixture_fallback: bool = True

    def __post_init__(self) -> None:
        self._templates = _TemplateCatalog.from_directory(TEMPLATE_DIR)

    async def search_aops(self, *, text: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        filter_clause = ""
        if text:
            filter_clause = (
                "FILTER (CONTAINS(LCASE(?title), LCASE(\"" + _escape_literal(text) + "\")))"
            )

        query = self._templates.render(
            "search_aops",
            {
                "filter_clause": filter_clause,
                "limit": limit,
            },
        )
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError:
            payload = self._load_fixture("aop_wiki", "search_aops")
        bindings = payload.get("results", {}).get("bindings", [])
        results: list[dict[str, Any]] = []
        for row in bindings:
            identifier = _normalize_binding_identifier(row, "aop")
            results.append(
                {
                    **identifier,
                    "title": _binding_value(row, "title"),
                    "short_name": _binding_value(row, "shortName"),
                }
            )
        return results

    async def get_aop(self, aop_id: str) -> dict[str, Any]:
        iri = self._aop_iri(aop_id)
        query = self._templates.render("get_aop", {"aop_iri": iri})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError:
            payload = self._load_fixture("aop_wiki", "get_aop")
        bindings = payload.get("results", {}).get("bindings", [])
        if not bindings:
            return {"id": _iri_to_curie(iri), "iri": iri}
        row = bindings[0]
        identifier = {"id": _iri_to_curie(iri), "iri": iri}
        return {
            **identifier,
            "title": _binding_value(row, "title"),
            "short_name": _binding_value(row, "shortName"),
            "status": _binding_value(row, "status"),
            "abstract": _binding_value(row, "abstract"),
        }

    async def list_key_events(self, aop_id: str) -> list[dict[str, Any]]:
        iri = self._aop_iri(aop_id)
        query = self._templates.render("list_key_events", {"aop_iri": iri})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError:
            payload = self._load_fixture("aop_wiki", "list_key_events")
        bindings = payload.get("results", {}).get("bindings", [])
        items: list[dict[str, Any]] = []
        for row in bindings:
            identifier = _normalize_binding_identifier(row, "ke")
            items.append(
                {
                    **identifier,
                    "title": _binding_value(row, "label"),
                    "event_type": _binding_value(row, "eventType"),
                }
            )
        return items

    async def list_kers(self, aop_id: str) -> list[dict[str, Any]]:
        iri = self._aop_iri(aop_id)
        query = self._templates.render("list_kers", {"aop_iri": iri})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError:
            payload = self._load_fixture("aop_wiki", "list_kers")
        bindings = payload.get("results", {}).get("bindings", [])
        items: list[dict[str, Any]] = []
        for row in bindings:
            identifier = _normalize_binding_identifier(row, "ker")
            upstream = _normalize_binding_identifier(row, "upstream")
            downstream = _normalize_binding_identifier(row, "downstream")
            items.append(
                {
                    **identifier,
                    "upstream": upstream,
                    "downstream": downstream,
                    "plausibility": _binding_value(row, "plausibility"),
                    "status": _binding_value(row, "status"),
                }
            )
        return items

    @staticmethod
    def _aop_iri(aop_id: str) -> str:
        if aop_id.startswith("http://") or aop_id.startswith("https://"):
            return aop_id
        if aop_id.upper().startswith("AOP:"):
            suffix = aop_id.split(":", 1)[1]
        else:
            suffix = aop_id
        return f"https://identifiers.org/aop/{suffix}"

    def _load_fixture(self, namespace: str, name: str) -> dict[str, Any]:
        if not self.enable_fixture_fallback:
            raise
        try:
            return load_fixture(namespace, name)
        except FixtureNotFoundError as exc:  # pragma: no cover - defensive fallback
            raise SparqlClientError(str(exc)) from exc
