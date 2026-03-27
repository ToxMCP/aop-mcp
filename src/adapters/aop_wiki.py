"""AOP-Wiki SPARQL adapter utilities."""

from __future__ import annotations

from dataclasses import dataclass
import html
from pathlib import Path
import re
from typing import Any

from .fixtures import FixtureNotFoundError, load_fixture
from .sparql_client import SparqlClient, SparqlClientError
from .sparql_client import TemplateCatalog as _TemplateCatalog

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "aop_wiki"

_SEARCH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "liver": ("hepatic",),
    "hepatic": ("liver",),
    "steatosis": ("fatty liver",),
    "fatty liver": ("steatosis",),
    "masld": (
        "non-alcoholic fatty liver disease",
        "nonalcoholic fatty liver disease",
        "metabolic dysfunction-associated steatotic liver disease",
    ),
    "nafld": (
        "masld",
        "non-alcoholic fatty liver disease",
        "nonalcoholic fatty liver disease",
    ),
    "nash": ("steatohepatitis", "nonalcoholic steatohepatitis"),
    "steatohepatitis": ("nash", "nonalcoholic steatohepatitis"),
}


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _normalize_search_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _expand_search_terms(text: str) -> list[str]:
    normalized = _normalize_search_text(text)
    if not normalized:
        return []

    expanded_terms: list[str] = []
    for candidate in [normalized, *re.split(r"\s+", normalized)]:
        if not candidate:
            continue
        if candidate not in expanded_terms:
            expanded_terms.append(candidate)
        for synonym in _SEARCH_SYNONYMS.get(candidate, ()):
            if synonym not in expanded_terms:
                expanded_terms.append(synonym)
    return expanded_terms


def _build_search_query_parts(text: str | None) -> dict[str, str]:
    if not text or not text.strip():
        return {
            "search_bindings": "BIND(0 AS ?surfaceMatchCount)\n  BIND(0 AS ?matchCount)\n  BIND(0 AS ?score)",
            "search_filter": "",
            "order_by": "LCASE(?title)",
        }

    normalized = _normalize_search_text(text)
    query_tokens = [token for token in re.split(r"\s+", normalized) if token]
    require_surface_matches = len(query_tokens) > 1

    match_terms: list[str] = []
    surface_match_terms: list[str] = []
    score_terms: list[str] = []
    for term in _expand_search_terms(text):
        escaped = _escape_literal(term)
        surface_match_terms.append(
            f'(IF(CONTAINS(LCASE(COALESCE(?title, "")), "{escaped}") || '
            f'CONTAINS(LCASE(COALESCE(?shortName, "")), "{escaped}"), 1, 0))'
        )
        match_terms.append(
            f'(IF(CONTAINS(LCASE(COALESCE(?title, "")), "{escaped}") || '
            f'CONTAINS(LCASE(COALESCE(?shortName, "")), "{escaped}") || '
            f'CONTAINS(LCASE(COALESCE(?abstract, "")), "{escaped}"), 1, 0))'
        )
        score_terms.append(
            f'(IF(CONTAINS(LCASE(COALESCE(?title, "")), "{escaped}"), 100, 0) + '
            f'IF(CONTAINS(LCASE(COALESCE(?shortName, "")), "{escaped}"), 70, 0) + '
            f'IF(CONTAINS(LCASE(COALESCE(?abstract, "")), "{escaped}"), 30, 0))'
        )

    return {
        "search_bindings": (
            f'BIND(({" + ".join(surface_match_terms)}) AS ?surfaceMatchCount)\n'
            f'  BIND(({" + ".join(match_terms)}) AS ?matchCount)\n'
            f'  BIND(({" + ".join(score_terms)}) AS ?score)'
        ),
        "search_filter": (
            "FILTER (?score > 0 && ?matchCount >= 1)"
            if not require_surface_matches
            else "FILTER (?score > 0 && ?surfaceMatchCount >= 2)"
        ),
        "order_by": "DESC(?surfaceMatchCount) DESC(?score) LCASE(?title)",
    }


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


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = html.unescape(value).replace("\xa0", " ")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _normalize_external_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("https://identifiers.org/"):
        tail = value.removeprefix("https://identifiers.org/")
        if "/" in tail:
            namespace, identifier = tail.split("/", 1)
            return f"{namespace.upper()}:{identifier}"
    if value.startswith("http://purl.obolibrary.org/obo/"):
        identifier = value.rsplit("/", 1)[-1]
        if "_" in identifier:
            namespace, local_id = identifier.split("_", 1)
            return f"{namespace}:{local_id}"
    if value.startswith("http://purl.bioontology.org/ontology/NCBITAXON/"):
        return f"NCBITaxon:{value.rsplit('/', 1)[-1]}"
    return _normalize_text(value)


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


def _append_unique(values: list[str], value: str | None) -> None:
    if value and value not in values:
        values.append(value)


def _append_unique_reference(values: list[dict[str, str | None]], reference: dict[str, str | None] | None) -> None:
    if not reference:
        return
    dedupe_key = (reference.get("identifier"), reference.get("label"), reference.get("source"))
    if any((item.get("identifier"), item.get("label"), item.get("source")) == dedupe_key for item in values):
        return
    values.append(reference)


def _identifier_from_reference_uri(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    normalized = value.strip()
    doi_prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "https://identifiers.org/doi/",
        "http://identifiers.org/doi/",
    )
    for prefix in doi_prefixes:
        if normalized.lower().startswith(prefix.lower()):
            return normalized[len(prefix):].rstrip(".,;)"), "doi"

    pmid_patterns = [
        (r"https?://pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?", "pmid"),
        (r"https?://identifiers\.org/pubmed/(\d+)", "pmid"),
        (r"https?://identifiers\.org/pmid/(\d+)", "pmid"),
    ]
    for pattern, source in pmid_patterns:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match:
            return f"PMID:{match.group(1)}", source

    if normalized.startswith(("http://", "https://")):
        return normalized, "uri"
    return normalized, "text"


def _normalize_reference_record(
    *,
    reference: str | None = None,
    label: str | None = None,
    citation_text: str | None = None,
) -> dict[str, str | None] | None:
    normalized_citation = _normalize_text(citation_text)
    normalized_reference = _normalize_text(reference)
    normalized_label = _normalize_text(label)

    if normalized_reference:
        identifier, source = _identifier_from_reference_uri(normalized_reference)
        return {
            "label": normalized_label or normalized_reference,
            "identifier": identifier,
            "source": source,
        }

    if normalized_citation:
        doi_match = re.search(r"\b10\.\S+\b", normalized_citation, re.IGNORECASE)
        pmid_match = re.search(r"\bPMID[:\s]+(\d+)\b", normalized_citation, re.IGNORECASE)
        if doi_match:
            return {
                "label": normalized_citation,
                "identifier": doi_match.group(0).rstrip(".,;)"),
                "source": "doi",
            }
        if pmid_match:
            return {
                "label": normalized_citation,
                "identifier": f"PMID:{pmid_match.group(1)}",
                "source": "pmid",
            }
        return {
            "label": normalized_citation,
            "identifier": None,
            "source": "citation_text",
        }

    return None


def _coalesce(record: dict[str, Any], key: str, value: str | None) -> None:
    if value is not None and record.get(key) is None:
        record[key] = value


@dataclass
class AOPWikiAdapter:
    """Adapter around the AOP-Wiki SPARQL endpoint."""

    client: SparqlClient
    cache_ttl_seconds: int = 300
    enable_fixture_fallback: bool = True

    def __post_init__(self) -> None:
        self._templates = _TemplateCatalog.from_directory(TEMPLATE_DIR)

    async def search_aops(self, *, text: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        search_query_parts = _build_search_query_parts(text)

        query = self._templates.render(
            "search_aops",
            {
                **search_query_parts,
                "limit": limit,
            },
        )
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_wiki", "search_aops", error=exc)
        bindings = payload.get("results", {}).get("bindings", [])
        results: list[dict[str, Any]] = []
        seen_identifiers: set[str] = set()
        for row in bindings:
            identifier = _normalize_binding_identifier(row, "aop")
            dedupe_key = identifier["id"] or identifier["iri"]
            if dedupe_key in seen_identifiers:
                continue
            if dedupe_key:
                seen_identifiers.add(dedupe_key)
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
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_wiki", "get_aop", error=exc)
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
            "references": [
                ref
                for ref in (
                    _normalize_reference_record(
                        reference=_binding_value(row, "reference"),
                        label=_binding_value(row, "referenceLabel"),
                        citation_text=_binding_value(row, "referenceText"),
                    ),
                )
                if ref
            ],
        }

    async def get_aop_assessment(self, aop_id: str) -> dict[str, Any]:
        iri = self._aop_iri(aop_id)
        query = self._templates.render("get_aop_assessment", {"aop_iri": iri})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_wiki", "get_aop_assessment", error=exc)
        bindings = payload.get("results", {}).get("bindings", [])
        record: dict[str, Any] = {
            "id": _iri_to_curie(iri),
            "iri": iri,
            "title": None,
            "short_name": None,
            "status": None,
            "abstract": None,
            "evidence_summary": None,
            "created": None,
            "modified": None,
            "molecular_initiating_events": [],
            "adverse_outcomes": [],
            "references": [],
        }
        seen_mies: set[str] = set()
        seen_aos: set[str] = set()

        for row in bindings:
            _coalesce(record, "title", _normalize_text(_binding_value(row, "title")))
            _coalesce(record, "short_name", _normalize_text(_binding_value(row, "shortName")))
            _coalesce(record, "status", _normalize_text(_binding_value(row, "status")))
            _coalesce(record, "abstract", _normalize_text(_binding_value(row, "abstract")))
            _coalesce(record, "evidence_summary", _normalize_text(_binding_value(row, "evidence")))
            _coalesce(record, "created", _normalize_text(_binding_value(row, "created")))
            _coalesce(record, "modified", _normalize_text(_binding_value(row, "modified")))

            mie = _normalize_binding_identifier(row, "mie")
            mie_key = mie["id"] or mie["iri"]
            if mie_key and mie_key not in seen_mies:
                seen_mies.add(mie_key)
                record["molecular_initiating_events"].append(
                    {
                        **mie,
                        "title": _normalize_text(_binding_value(row, "mieTitle")),
                    }
                )

            ao = _normalize_binding_identifier(row, "ao")
            ao_key = ao["id"] or ao["iri"]
            if ao_key and ao_key not in seen_aos:
                seen_aos.add(ao_key)
                record["adverse_outcomes"].append(
                    {
                        **ao,
                        "title": _normalize_text(_binding_value(row, "aoTitle")),
                    }
                )

            _append_unique_reference(
                record["references"],
                _normalize_reference_record(
                    reference=_binding_value(row, "reference"),
                    label=_binding_value(row, "referenceLabel"),
                    citation_text=_binding_value(row, "referenceText"),
                ),
            )

        return record

    async def list_key_events(self, aop_id: str) -> list[dict[str, Any]]:
        iri = self._aop_iri(aop_id)
        query = self._templates.render("list_key_events", {"aop_iri": iri})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_wiki", "list_key_events", error=exc)
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

    async def get_key_event(self, ke_id: str) -> dict[str, Any]:
        iri = self._event_iri(ke_id)
        query = self._templates.render("get_key_event", {"ke_iri": iri})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_wiki", "get_key_event", error=exc)
        bindings = payload.get("results", {}).get("bindings", [])
        record: dict[str, Any] = {
            "id": _iri_to_curie(iri),
            "iri": iri,
            "title": None,
            "short_name": None,
            "description": None,
            "level_of_biological_organization": None,
            "direction_of_change": None,
            "sex_applicability": None,
            "life_stage_applicability": None,
            "measurement_methods": [],
            "taxonomic_applicability": [],
            "gene_identifiers": [],
            "protein_identifiers": [],
            "biological_processes": [],
            "cell_type_context": [],
            "organ_context": [],
            "part_of_aops": [],
            "references": [],
        }
        seen_aops: set[str] = set()

        for row in bindings:
            _coalesce(record, "title", _normalize_text(_binding_value(row, "title")))
            _coalesce(record, "short_name", _normalize_text(_binding_value(row, "shortName")))
            _coalesce(record, "description", _normalize_text(_binding_value(row, "description")))
            _coalesce(
                record,
                "level_of_biological_organization",
                _normalize_text(_binding_value(row, "level")),
            )
            _coalesce(record, "direction_of_change", _normalize_text(_binding_value(row, "direction")))
            _coalesce(record, "sex_applicability", _normalize_text(_binding_value(row, "sex")))
            _coalesce(
                record,
                "life_stage_applicability",
                _normalize_text(_binding_value(row, "lifeStage")),
            )

            _append_unique(
                record["measurement_methods"],
                _normalize_text(_binding_value(row, "measurement")),
            )
            _append_unique(
                record["gene_identifiers"],
                _normalize_external_identifier(_binding_value(row, "gene")),
            )
            _append_unique(
                record["protein_identifiers"],
                _normalize_external_identifier(_binding_value(row, "protein")),
            )
            _append_unique(
                record["biological_processes"],
                _normalize_external_identifier(_binding_value(row, "biologicalProcess")),
            )
            _append_unique(
                record["cell_type_context"],
                _normalize_external_identifier(_binding_value(row, "cellType")),
            )
            _append_unique(
                record["organ_context"],
                _normalize_external_identifier(_binding_value(row, "organ")),
            )

            taxon = _normalize_external_identifier(_binding_value(row, "taxon"))
            if taxon and taxon.startswith("NCBITaxon:"):
                _append_unique(record["taxonomic_applicability"], taxon)

            aop_identifier = _normalize_binding_identifier(row, "aop")
            aop_key = aop_identifier["id"] or aop_identifier["iri"]
            if aop_key and aop_key not in seen_aops:
                seen_aops.add(aop_key)
                record["part_of_aops"].append(
                    {
                        **aop_identifier,
                        "title": _normalize_text(_binding_value(row, "aopTitle")),
                    }
                )

            _append_unique_reference(
                record["references"],
                _normalize_reference_record(
                    reference=_binding_value(row, "reference"),
                    label=_binding_value(row, "referenceLabel"),
                    citation_text=_binding_value(row, "referenceText"),
                ),
            )

        record["shared_aop_count"] = len(record["part_of_aops"])
        return record

    async def list_kers(self, aop_id: str) -> list[dict[str, Any]]:
        iri = self._aop_iri(aop_id)
        query = self._templates.render("list_kers", {"aop_iri": iri})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_wiki", "list_kers", error=exc)
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

    async def get_ker(self, ker_id: str) -> dict[str, Any]:
        iri = self._ker_iri(ker_id)
        query = self._templates.render("get_ker", {"ker_iri": iri})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_wiki", "get_ker", error=exc)
        bindings = payload.get("results", {}).get("bindings", [])
        record: dict[str, Any] = {
            "id": _iri_to_curie(iri),
            "iri": iri,
            "title": None,
            "description": None,
            "biological_plausibility": None,
            "empirical_support": None,
            "quantitative_understanding": None,
            "created": None,
            "modified": None,
            "gene_identifiers": [],
            "referenced_aops": [],
            "upstream": {"id": None, "iri": None, "title": None},
            "downstream": {"id": None, "iri": None, "title": None},
            "references": [],
        }
        seen_aops: set[str] = set()

        for row in bindings:
            upstream = _normalize_binding_identifier(row, "upstream")
            downstream = _normalize_binding_identifier(row, "downstream")
            if upstream["id"] or upstream["iri"]:
                record["upstream"] = {
                    **upstream,
                    "title": _normalize_text(_binding_value(row, "upstreamTitle")),
                }
            if downstream["id"] or downstream["iri"]:
                record["downstream"] = {
                    **downstream,
                    "title": _normalize_text(_binding_value(row, "downstreamTitle")),
                }

            _coalesce(record, "description", _normalize_text(_binding_value(row, "description")))
            _coalesce(
                record,
                "biological_plausibility",
                _normalize_text(_binding_value(row, "plausibility")),
            )
            _coalesce(
                record,
                "empirical_support",
                _normalize_text(_binding_value(row, "empiricalSupport")),
            )
            _coalesce(
                record,
                "quantitative_understanding",
                _normalize_text(_binding_value(row, "quantitativeUnderstanding")),
            )
            _coalesce(record, "created", _normalize_text(_binding_value(row, "created")))
            _coalesce(record, "modified", _normalize_text(_binding_value(row, "modified")))
            _append_unique(
                record["gene_identifiers"],
                _normalize_external_identifier(_binding_value(row, "gene")),
            )

            aop_identifier = _normalize_binding_identifier(row, "aop")
            aop_key = aop_identifier["id"] or aop_identifier["iri"]
            if aop_key and aop_key not in seen_aops:
                seen_aops.add(aop_key)
                record["referenced_aops"].append(
                    {
                        **aop_identifier,
                        "title": _normalize_text(_binding_value(row, "aopTitle")),
                    }
                )

            _append_unique_reference(
                record["references"],
                _normalize_reference_record(
                    reference=_binding_value(row, "reference"),
                    label=_binding_value(row, "referenceLabel"),
                    citation_text=_binding_value(row, "referenceText"),
                ),
            )

        if record["title"] is None:
            upstream_title = record["upstream"].get("title")
            downstream_title = record["downstream"].get("title")
            if upstream_title and downstream_title:
                record["title"] = f"{upstream_title} leads to {downstream_title}"
        record["shared_aop_count"] = len(record["referenced_aops"])
        return record

    async def get_related_aops(self, aop_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        iri = self._aop_iri(aop_id)
        query = self._templates.render("get_related_aops", {"aop_iri": iri, "limit": limit})
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_wiki", "get_related_aops", error=exc)
        bindings = payload.get("results", {}).get("bindings", [])
        results: list[dict[str, Any]] = []
        for row in bindings:
            identifier = _normalize_binding_identifier(row, "relatedAop")
            shared_ke_count = int(_binding_value(row, "sharedKeCount") or 0)
            shared_ker_count = int(_binding_value(row, "sharedKerCount") or 0)
            results.append(
                {
                    **identifier,
                    "title": _normalize_text(_binding_value(row, "title")),
                    "shared_key_event_count": shared_ke_count,
                    "shared_ker_count": shared_ker_count,
                    "total_shared_elements": shared_ke_count + shared_ker_count,
                }
            )
        return results

    @staticmethod
    def _aop_iri(aop_id: str) -> str:
        if aop_id.startswith("http://") or aop_id.startswith("https://"):
            return aop_id
        if aop_id.upper().startswith("AOP:"):
            suffix = aop_id.split(":", 1)[1]
        else:
            suffix = aop_id
        return f"https://identifiers.org/aop/{suffix}"

    @staticmethod
    def _event_iri(ke_id: str) -> str:
        if ke_id.startswith("http://") or ke_id.startswith("https://"):
            return ke_id
        suffix = ke_id.split(":", 1)[1] if ke_id.upper().startswith("KE:") else ke_id
        return f"https://identifiers.org/aop.events/{suffix}"

    @staticmethod
    def _ker_iri(ker_id: str) -> str:
        if ker_id.startswith("http://") or ker_id.startswith("https://"):
            return ker_id
        suffix = ker_id.split(":", 1)[1] if ker_id.upper().startswith("KER:") else ker_id
        return f"https://identifiers.org/aop.relationships/{suffix}"

    def _load_fixture(
        self,
        namespace: str,
        name: str,
        *,
        error: SparqlClientError | None = None,
    ) -> dict[str, Any]:
        if not self.enable_fixture_fallback:
            if error is not None:
                raise error
            raise SparqlClientError("Fixture fallback requested without an underlying SPARQL error")
        try:
            return load_fixture(namespace, name)
        except FixtureNotFoundError as exc:  # pragma: no cover - defensive fallback
            raise SparqlClientError(str(exc)) from exc
