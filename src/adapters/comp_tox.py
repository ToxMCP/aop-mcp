"""CompTox Dashboard client for chemical metadata mapping."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any
from urllib.parse import quote

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
        self._assay_catalog_items_cache: list[dict[str, Any]] | None = None

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
            headers["x-api-key"] = self._api_key
        return headers

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

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

    def search_equal(self, value: str) -> list[dict[str, Any]]:
        response = self._bio_client.get(
            f"chemical/search/equal/{quote(value, safe='')}",
            headers=self._headers(),
        )
        payload = self._handle_response(response)
        if payload is None:
            return []
        return payload if isinstance(payload, list) else []

    def bioactivity_data_by_dtxsid(self, dtxsid: str) -> list[dict[str, Any]]:
        response = self._bio_client.get(
            f"bioactivity/data/search/by-dtxsid/{quote(dtxsid, safe='')}",
            headers=self._headers(),
        )
        payload = self._handle_response(response)
        if payload is None:
            return []
        return payload if isinstance(payload, list) else []

    def assay_by_aeid(self, aeid: int) -> dict[str, Any] | None:
        response = self._bio_client.get(
            f"bioactivity/assay/search/by-aeid/{aeid}",
            headers=self._headers(),
        )
        payload = self._handle_response(response)
        if payload is None:
            return None
        if isinstance(payload, list):
            return payload[0] if payload else None
        return payload if isinstance(payload, dict) else None

    def assay_catalog_items(self) -> list[dict[str, Any]]:
        if self._assay_catalog_items_cache is not None:
            return self._assay_catalog_items_cache

        html = self._fetch_assay_catalog_html()
        self._assay_catalog_items_cache = self._parse_assay_catalog_items(html)
        return self._assay_catalog_items_cache

    def search_assay_catalog(
        self,
        *,
        gene_symbols: list[str] | None = None,
        phrases: list[str] | None = None,
        preferred_taxa: list[str] | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        normalized_gene_symbols = []
        for value in gene_symbols or []:
            normalized = value.strip().upper()
            if normalized and normalized not in normalized_gene_symbols:
                normalized_gene_symbols.append(normalized)

        normalized_phrases = []
        for value in phrases or []:
            normalized = _normalize_catalog_text(value)
            if normalized and normalized not in normalized_phrases:
                normalized_phrases.append(normalized)

        normalized_preferred_taxa = []
        for value in preferred_taxa or []:
            normalized = _normalize_taxon_name(value)
            if normalized and normalized not in normalized_preferred_taxa:
                normalized_preferred_taxa.append(normalized)

        if not normalized_gene_symbols and not normalized_phrases:
            return []

        ranked_items: dict[int, dict[str, Any]] = {}
        for item in self.assay_catalog_items():
            aeid = item.get("aeid")
            if aeid is None:
                continue
            aeid_int = int(aeid)
            assay_name = item.get("assayName")
            endpoint_name = item.get("assayComponentEndpointName")
            desc_text = item.get("assayComponentEndpointDesc")
            detail_text = item.get("ccdAssayDetail")
            item_text = " ".join(
                filter(
                    None,
                    [
                        _normalize_catalog_text(assay_name),
                        _normalize_catalog_text(endpoint_name),
                        _normalize_catalog_text(desc_text),
                        _normalize_catalog_text(detail_text),
                    ],
                )
            )

            item_gene_symbols = {
                entry.get("geneSymbol", "").strip().upper()
                for entry in _iter_assay_gene_entries(item)
                if entry.get("geneSymbol")
            }
            item_gene_names = {
                _normalize_catalog_text(entry.get("geneName"))
                for entry in _iter_assay_gene_entries(item)
                if entry.get("geneName")
            }
            item_taxon_name = _normalize_taxon_name(item.get("taxonName"))

            score = 0
            matched_terms: set[str] = set()
            match_basis: set[str] = set()
            matched_taxa: set[str] = set()

            for symbol in normalized_gene_symbols:
                symbol_text = symbol.lower()
                if symbol in item_gene_symbols:
                    score += 120
                    matched_terms.add(symbol)
                    match_basis.add("gene_symbol_exact")
                if assay_name and symbol_text in assay_name.lower():
                    score += 70
                    matched_terms.add(symbol)
                    match_basis.add("assay_name")
                elif endpoint_name and symbol_text in endpoint_name.lower():
                    score += 70
                    matched_terms.add(symbol)
                    match_basis.add("assay_endpoint")
                elif symbol_text in item_text:
                    score += 35
                    matched_terms.add(symbol)
                    match_basis.add("assay_description")

            for phrase in normalized_phrases:
                if phrase in item_gene_names:
                    score += 90
                    matched_terms.add(phrase)
                    match_basis.add("gene_name_exact")
                if assay_name and phrase in _normalize_catalog_text(assay_name):
                    score += 55
                    matched_terms.add(phrase)
                    match_basis.add("assay_name_phrase")
                elif endpoint_name and phrase in _normalize_catalog_text(endpoint_name):
                    score += 55
                    matched_terms.add(phrase)
                    match_basis.add("assay_endpoint_phrase")
                elif phrase in item_text:
                    score += 25
                    matched_terms.add(phrase)
                    match_basis.add("assay_description_phrase")

            if score <= 0:
                continue

            applicability_match = "unknown"
            if normalized_preferred_taxa:
                applicability_match = "mismatch" if item_taxon_name else "unknown"
                for preferred_taxon in normalized_preferred_taxa:
                    if _taxon_matches(item_taxon_name, preferred_taxon):
                        score += 30
                        matched_taxa.add(preferred_taxon)
                        match_basis.add("taxonomic_applicability_match")
                        applicability_match = "match"

            score += min(int(item.get("multi_conc_assay_chemical_count_active") or 0) // 250, 20)
            candidate = ranked_items.setdefault(
                aeid_int,
                {
                    "aeid": aeid_int,
                    "catalog_item": item,
                    "match_score": score,
                    "matched_terms": set(matched_terms),
                    "match_basis": set(match_basis),
                    "matched_taxa": set(matched_taxa),
                    "applicability_match": applicability_match,
                },
            )
            if score > candidate["match_score"]:
                candidate["catalog_item"] = item
                candidate["match_score"] = score
                candidate["applicability_match"] = applicability_match
            candidate["matched_terms"].update(matched_terms)
            candidate["match_basis"].update(match_basis)
            candidate["matched_taxa"].update(matched_taxa)

        ranked_candidates = sorted(
            ranked_items.values(),
            key=lambda item: (
                -item["match_score"],
                -int(item["catalog_item"].get("multi_conc_assay_chemical_count_active") or 0),
                -int(item["catalog_item"].get("multi_conc_assay_chemical_count_total") or 0),
                item["aeid"],
            ),
        )[:limit]

        results: list[dict[str, Any]] = []
        for candidate in ranked_candidates:
            catalog_item = candidate["catalog_item"]
            try:
                assay = self.assay_by_aeid(candidate["aeid"]) or {}
            except CompToxError:
                assay = {}
            assay_genes = assay.get("gene") or []
            gene_symbols_out = sorted(
                {
                    gene.get("geneSymbol")
                    for gene in assay_genes
                    if gene.get("geneSymbol")
                }
                or {
                    entry.get("geneSymbol")
                    for entry in _iter_assay_gene_entries(catalog_item)
                    if entry.get("geneSymbol")
                }
            )
            results.append(
                {
                    "aeid": candidate["aeid"],
                    "assay_name": assay.get("assayName") or catalog_item.get("assayName"),
                    "assay_component_endpoint_name": assay.get("assayComponentEndpointName")
                    or catalog_item.get("assayComponentEndpointName"),
                    "assay_component_endpoint_desc": assay.get("assayComponentEndpointDesc")
                    or catalog_item.get("assayComponentEndpointDesc"),
                    "assay_function_type": assay.get("assayFunctionType"),
                    "target_family": assay.get("intendedTargetFamily"),
                    "target_family_sub": assay.get("intendedTargetFamilySub"),
                    "target_type": assay.get("intendedTargetType"),
                    "gene_symbols": gene_symbols_out,
                    "taxon_name": catalog_item.get("taxonName"),
                    "applicability_match": candidate["applicability_match"],
                    "matched_taxa": sorted(candidate["matched_taxa"]),
                    "match_score": candidate["match_score"],
                    "match_basis": sorted(candidate["match_basis"]),
                    "matched_terms": sorted(candidate["matched_terms"]),
                    "multi_conc_assay_chemical_count_active": catalog_item.get(
                        "multi_conc_assay_chemical_count_active"
                    ),
                    "multi_conc_assay_chemical_count_total": catalog_item.get(
                        "multi_conc_assay_chemical_count_total"
                    ),
                    "single_conc_assay_chemical_count_active": catalog_item.get(
                        "single_conc_assay_chemical_count_active"
                    ),
                    "single_conc_assay_chemical_count_total": catalog_item.get(
                        "single_conc_assay_chemical_count_total"
                    ),
                    "source": "comptox_assay_catalog",
                }
            )
        return results

    def _fetch_assay_catalog_html(self) -> str:
        response = self._client.get(self._dashboard_assay_catalog_url(), headers={"Accept": "text/html"})
        if response.status_code >= 400:
            raise CompToxError(
                f"CompTox assay catalog request failed: {response.status_code} {response.text}"
            )
        return response.text

    def _dashboard_assay_catalog_url(self) -> str:
        base_url = str(self._client.base_url).rstrip("/")
        if base_url.endswith("/api"):
            base_url = base_url[: -len("/api")]
        return f"{base_url}/assay-endpoints"

    def _parse_assay_catalog_items(self, html: str) -> list[dict[str, Any]]:
        node_path = shutil.which("node")
        if not node_path:
            raise CompToxError(
                "Node.js is required to parse the CompTox assay catalog page for key-event assay search"
            )

        parser_script = r"""
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(0, 'utf8');
const start = html.indexOf('window.__NUXT__=');
if (start === -1) {
  throw new Error('CompTox assay catalog page did not contain window.__NUXT__');
}
const end = html.indexOf('</script>', start);
const script = html.slice(start, end);
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(script, sandbox, { timeout: 15000 });
const nuxt = sandbox.window.__NUXT__ || {};
const items = (((nuxt.state || {}).assayEndpoints || {}).assayEndpointItems) || [];
process.stdout.write(JSON.stringify(items));
"""
        try:
            completed = subprocess.run(
                [node_path, "-e", parser_script],
                input=html,
                text=True,
                capture_output=True,
                check=True,
                timeout=20,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise CompToxError("Failed to parse CompTox assay catalog page") from exc
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise CompToxError("CompTox assay catalog parser returned invalid JSON") from exc
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


def _normalize_catalog_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.replace("\r", " ").replace("\n", " ").replace("-", " ")
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _iter_assay_gene_entries(item: dict[str, Any]) -> list[dict[str, Any]]:
    genes = item.get("genes") or item.get("geneArray") or []
    return [entry for entry in genes if isinstance(entry, dict)]


def _normalize_taxon_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = _normalize_catalog_text(value)
    synonyms = {
        "homo sapiens": "human",
        "human": "human",
        "mus musculus": "mouse",
        "mouse": "mouse",
        "mice": "mouse",
        "rattus norvegicus": "rat",
        "rat": "rat",
    }
    return synonyms.get(normalized, normalized)


def _taxon_matches(item_taxon: str, preferred_taxon: str) -> bool:
    if not item_taxon or not preferred_taxon:
        return False
    return item_taxon == preferred_taxon
