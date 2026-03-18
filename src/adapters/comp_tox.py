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
        self._all_assays_cache: list[dict[str, Any]] | None = None

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

    def assays_by_gene(self, gene_symbol: str) -> list[dict[str, Any]]:
        response = self._bio_client.get(
            f"bioactivity/assay/search/by-gene/{quote(gene_symbol, safe='')}",
            headers=self._headers(),
        )
        payload = self._handle_response(response)
        if payload is None:
            return []
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return [payload] if isinstance(payload, dict) else []

    def all_assays(self) -> list[dict[str, Any]]:
        if self._all_assays_cache is not None:
            return self._all_assays_cache

        response = self._bio_client.get("bioactivity/assay/", headers=self._headers())
        payload = self._handle_response(response)
        if payload is None:
            self._all_assays_cache = []
        elif isinstance(payload, list):
            self._all_assays_cache = [row for row in payload if isinstance(row, dict)]
        elif isinstance(payload, dict):
            self._all_assays_cache = [payload]
        else:
            self._all_assays_cache = []
        return self._all_assays_cache

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

        direct_search_errors: list[str] = []
        if normalized_gene_symbols:
            try:
                direct_results = self._search_assays_by_gene_api(
                    gene_symbols=normalized_gene_symbols,
                    phrases=normalized_phrases,
                    preferred_taxa=normalized_preferred_taxa,
                    limit=limit,
                )
            except CompToxError as exc:
                direct_search_errors.append(str(exc))
            else:
                if direct_results:
                    return direct_results

        all_assays_available = False
        try:
            api_results = self._search_assays_from_full_api(
                gene_symbols=normalized_gene_symbols,
                phrases=normalized_phrases,
                preferred_taxa=normalized_preferred_taxa,
                limit=limit,
            )
        except CompToxError as exc:
            direct_search_errors.append(str(exc))
        else:
            all_assays_available = True
            if api_results:
                return api_results

        if all_assays_available:
            return []

        try:
            catalog_items = self.assay_catalog_items()
        except CompToxError as exc:
            if direct_search_errors:
                detail = "; ".join(direct_search_errors)
                raise CompToxError(
                    f"CompTox direct gene assay search failed ({detail}); assay catalog fallback failed: {exc}"
                ) from exc
            raise

        ranked_items: dict[int, dict[str, Any]] = {}
        for item in catalog_items:
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

        if not results and direct_search_errors:
            raise CompToxError("; ".join(direct_search_errors))
        return results

    def _search_assays_by_gene_api(
        self,
        *,
        gene_symbols: list[str],
        phrases: list[str],
        preferred_taxa: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        ranked_items: dict[int, dict[str, Any]] = {}
        assay_cache: dict[int, dict[str, Any]] = {}
        errors: list[str] = []

        for symbol in gene_symbols:
            try:
                rows = self.assays_by_gene(symbol)
            except CompToxError as exc:
                errors.append(f"{symbol}: {exc}")
                continue

            for row in rows:
                aeid = row.get("aeid")
                if aeid is None:
                    continue
                aeid_int = int(aeid)
                assay = assay_cache.get(aeid_int)
                if assay is None:
                    try:
                        assay = self.assay_by_aeid(aeid_int) or {}
                    except CompToxError:
                        assay = {}
                    assay_cache[aeid_int] = assay

                assay_name = assay.get("assayName") or row.get("assayName") or row.get("assayComponentEndpointName")
                endpoint_name = assay.get("assayComponentEndpointName") or row.get("assayComponentEndpointName")
                desc_text = assay.get("assayComponentEndpointDesc") or row.get("assayComponentEndpointDesc")
                item_text = " ".join(
                    filter(
                        None,
                        [
                            _normalize_catalog_text(assay_name),
                            _normalize_catalog_text(endpoint_name),
                            _normalize_catalog_text(desc_text),
                            _normalize_catalog_text(assay.get("assayComponentDesc")),
                            _normalize_catalog_text(assay.get("assayComponentTargetDesc")),
                        ],
                    )
                )
                assay_gene_entries = _iter_assay_gene_entries(assay)
                item_gene_symbols = {
                    gene.get("geneSymbol", "").strip().upper()
                    for gene in assay_gene_entries
                    if gene.get("geneSymbol")
                }
                if row.get("geneSymbol"):
                    item_gene_symbols.add(str(row["geneSymbol"]).strip().upper())
                item_gene_names = {
                    _normalize_catalog_text(gene.get("geneName"))
                    for gene in assay_gene_entries
                    if gene.get("geneName")
                }
                item_taxon_name = _normalize_taxon_name(assay.get("organism") or assay.get("taxonName"))

                score = 160
                matched_terms: set[str] = {symbol}
                match_basis: set[str] = {"ctx_gene_search_exact"}
                matched_taxa: set[str] = set()

                for other_symbol in gene_symbols:
                    if other_symbol == symbol:
                        continue
                    other_symbol_text = other_symbol.lower()
                    if other_symbol in item_gene_symbols:
                        score += 120
                        matched_terms.add(other_symbol)
                        match_basis.add("gene_symbol_exact")
                    if assay_name and other_symbol_text in assay_name.lower():
                        score += 70
                        matched_terms.add(other_symbol)
                        match_basis.add("assay_name")
                    elif endpoint_name and other_symbol_text in endpoint_name.lower():
                        score += 70
                        matched_terms.add(other_symbol)
                        match_basis.add("assay_endpoint")
                    elif other_symbol_text in item_text:
                        score += 35
                        matched_terms.add(other_symbol)
                        match_basis.add("assay_description")

                for phrase in phrases:
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

                applicability_match = "unknown"
                if preferred_taxa:
                    applicability_match = "mismatch" if item_taxon_name else "unknown"
                    for preferred_taxon in preferred_taxa:
                        if _taxon_matches(item_taxon_name, preferred_taxon):
                            score += 30
                            matched_taxa.add(preferred_taxon)
                            match_basis.add("taxonomic_applicability_match")
                            applicability_match = "match"

                multi_active, multi_total = _parse_activity_summary(row.get("multiConcActives"))
                single_active, single_total = _parse_activity_summary(row.get("singleConcActive"))
                score += min((multi_active or 0) // 250, 20)

                candidate = ranked_items.setdefault(
                    aeid_int,
                    {
                        "aeid": aeid_int,
                        "row": row,
                        "assay": assay,
                        "taxon_name": assay.get("organism") or assay.get("taxonName"),
                        "applicability_match": applicability_match,
                        "match_score": score,
                        "matched_terms": set(matched_terms),
                        "match_basis": set(match_basis),
                        "matched_taxa": set(matched_taxa),
                        "multi_conc_assay_chemical_count_active": multi_active,
                        "multi_conc_assay_chemical_count_total": multi_total,
                        "single_conc_assay_chemical_count_active": single_active,
                        "single_conc_assay_chemical_count_total": single_total,
                    },
                )
                if score > candidate["match_score"]:
                    candidate["row"] = row
                    candidate["assay"] = assay
                    candidate["taxon_name"] = assay.get("organism") or assay.get("taxonName")
                    candidate["applicability_match"] = applicability_match
                    candidate["match_score"] = score
                    candidate["multi_conc_assay_chemical_count_active"] = multi_active
                    candidate["multi_conc_assay_chemical_count_total"] = multi_total
                    candidate["single_conc_assay_chemical_count_active"] = single_active
                    candidate["single_conc_assay_chemical_count_total"] = single_total
                candidate["matched_terms"].update(matched_terms)
                candidate["match_basis"].update(match_basis)
                candidate["matched_taxa"].update(matched_taxa)

        ranked_candidates = sorted(
            ranked_items.values(),
            key=lambda item: (
                -item["match_score"],
                -int(item.get("multi_conc_assay_chemical_count_active") or 0),
                -int(item.get("multi_conc_assay_chemical_count_total") or 0),
                item["aeid"],
            ),
        )[:limit]

        results: list[dict[str, Any]] = []
        for candidate in ranked_candidates:
            assay = candidate["assay"] or {}
            row = candidate["row"]
            fallback_gene_symbols = {str(row["geneSymbol"]).strip().upper()} if row.get("geneSymbol") else set()
            gene_symbols_out = sorted(
                {
                    gene.get("geneSymbol")
                    for gene in assay.get("gene") or []
                    if gene.get("geneSymbol")
                }
                or fallback_gene_symbols
            )
            results.append(
                {
                    "aeid": candidate["aeid"],
                    "assay_name": assay.get("assayName") or row.get("assayName") or row.get("assayComponentEndpointName"),
                    "assay_component_endpoint_name": assay.get("assayComponentEndpointName")
                    or row.get("assayComponentEndpointName"),
                    "assay_component_endpoint_desc": assay.get("assayComponentEndpointDesc")
                    or row.get("assayComponentEndpointDesc"),
                    "assay_function_type": assay.get("assayFunctionType"),
                    "target_family": assay.get("intendedTargetFamily"),
                    "target_family_sub": assay.get("intendedTargetFamilySub"),
                    "target_type": assay.get("intendedTargetType"),
                    "gene_symbols": gene_symbols_out,
                    "taxon_name": candidate["taxon_name"],
                    "applicability_match": candidate["applicability_match"],
                    "matched_taxa": sorted(candidate["matched_taxa"]),
                    "match_score": candidate["match_score"],
                    "match_basis": sorted(candidate["match_basis"]),
                    "matched_terms": sorted(candidate["matched_terms"]),
                    "multi_conc_assay_chemical_count_active": candidate["multi_conc_assay_chemical_count_active"],
                    "multi_conc_assay_chemical_count_total": candidate["multi_conc_assay_chemical_count_total"],
                    "single_conc_assay_chemical_count_active": candidate["single_conc_assay_chemical_count_active"],
                    "single_conc_assay_chemical_count_total": candidate["single_conc_assay_chemical_count_total"],
                    "source": "comptox_assay_gene_api",
                }
            )

        if results:
            return results
        if errors:
            raise CompToxError("; ".join(errors))
        return []

    def _search_assays_from_full_api(
        self,
        *,
        gene_symbols: list[str],
        phrases: list[str],
        preferred_taxa: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        ranked_items: dict[int, dict[str, Any]] = {}
        for assay in self.all_assays():
            aeid = assay.get("aeid")
            if aeid is None:
                continue
            aeid_int = int(aeid)
            assay_name = assay.get("assayName") or assay.get("assayComponentName")
            endpoint_name = assay.get("assayComponentEndpointName")
            desc_text = assay.get("assayComponentEndpointDesc")
            detail_text = " ".join(
                filter(
                    None,
                    [
                        assay.get("assayComponentDesc"),
                        assay.get("assayComponentTargetDesc"),
                        assay.get("assayDesc"),
                        _flatten_assay_list(assay.get("assayList")),
                    ],
                )
            )
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
                for entry in _iter_assay_gene_entries(assay)
                if entry.get("geneSymbol")
            }
            item_gene_names = {
                _normalize_catalog_text(entry.get("geneName"))
                for entry in _iter_assay_gene_entries(assay)
                if entry.get("geneName")
            }
            item_taxon_name = _normalize_taxon_name(assay.get("organism") or assay.get("taxonName"))

            score = 0
            matched_terms: set[str] = set()
            match_basis: set[str] = set()
            matched_taxa: set[str] = set()

            for symbol in gene_symbols:
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

            for phrase in phrases:
                phrase_score, phrase_basis, phrase_terms = _score_phrase_match(
                    phrase=phrase,
                    assay_name=assay_name,
                    endpoint_name=endpoint_name,
                    item_text=item_text,
                    item_gene_names=item_gene_names,
                )
                score += phrase_score
                matched_terms.update(phrase_terms)
                match_basis.update(phrase_basis)

            if score <= 0:
                continue

            applicability_match = "unknown"
            if preferred_taxa:
                applicability_match = "mismatch" if item_taxon_name else "unknown"
                for preferred_taxon in preferred_taxa:
                    if _taxon_matches(item_taxon_name, preferred_taxon):
                        score += 30
                        matched_taxa.add(preferred_taxon)
                        match_basis.add("taxonomic_applicability_match")
                        applicability_match = "match"

            multi_active, multi_total = _parse_activity_summary(assay.get("multiConcActives"))
            single_active, single_total = _parse_activity_summary(assay.get("singleConcActive"))
            score += min((multi_active or 0) // 250, 20)

            candidate = ranked_items.setdefault(
                aeid_int,
                {
                    "aeid": aeid_int,
                    "assay": assay,
                    "taxon_name": assay.get("organism") or assay.get("taxonName"),
                    "applicability_match": applicability_match,
                    "match_score": score,
                    "matched_terms": set(matched_terms),
                    "match_basis": set(match_basis),
                    "matched_taxa": set(matched_taxa),
                    "multi_conc_assay_chemical_count_active": multi_active,
                    "multi_conc_assay_chemical_count_total": multi_total,
                    "single_conc_assay_chemical_count_active": single_active,
                    "single_conc_assay_chemical_count_total": single_total,
                },
            )
            if score > candidate["match_score"]:
                candidate["assay"] = assay
                candidate["taxon_name"] = assay.get("organism") or assay.get("taxonName")
                candidate["applicability_match"] = applicability_match
                candidate["match_score"] = score
                candidate["multi_conc_assay_chemical_count_active"] = multi_active
                candidate["multi_conc_assay_chemical_count_total"] = multi_total
                candidate["single_conc_assay_chemical_count_active"] = single_active
                candidate["single_conc_assay_chemical_count_total"] = single_total
            candidate["matched_terms"].update(matched_terms)
            candidate["match_basis"].update(match_basis)
            candidate["matched_taxa"].update(matched_taxa)

        ranked_candidates = sorted(
            ranked_items.values(),
            key=lambda item: (
                -item["match_score"],
                -int(item.get("multi_conc_assay_chemical_count_active") or 0),
                -int(item.get("multi_conc_assay_chemical_count_total") or 0),
                item["aeid"],
            ),
        )[:limit]

        results: list[dict[str, Any]] = []
        for candidate in ranked_candidates:
            assay = candidate["assay"]
            gene_symbols_out = sorted(
                {
                    gene.get("geneSymbol")
                    for gene in assay.get("gene") or []
                    if gene.get("geneSymbol")
                }
            )
            results.append(
                {
                    "aeid": candidate["aeid"],
                    "assay_name": assay.get("assayName") or assay.get("assayComponentName"),
                    "assay_component_endpoint_name": assay.get("assayComponentEndpointName"),
                    "assay_component_endpoint_desc": assay.get("assayComponentEndpointDesc"),
                    "assay_function_type": assay.get("assayFunctionType"),
                    "target_family": assay.get("intendedTargetFamily"),
                    "target_family_sub": assay.get("intendedTargetFamilySub"),
                    "target_type": assay.get("intendedTargetType"),
                    "gene_symbols": gene_symbols_out,
                    "taxon_name": candidate["taxon_name"],
                    "applicability_match": candidate["applicability_match"],
                    "matched_taxa": sorted(candidate["matched_taxa"]),
                    "match_score": candidate["match_score"],
                    "match_basis": sorted(candidate["match_basis"]),
                    "matched_terms": sorted(candidate["matched_terms"]),
                    "multi_conc_assay_chemical_count_active": candidate["multi_conc_assay_chemical_count_active"],
                    "multi_conc_assay_chemical_count_total": candidate["multi_conc_assay_chemical_count_total"],
                    "single_conc_assay_chemical_count_active": candidate["single_conc_assay_chemical_count_active"],
                    "single_conc_assay_chemical_count_total": candidate["single_conc_assay_chemical_count_total"],
                    "source": "comptox_assay_api",
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
    genes = item.get("genes") or item.get("geneArray") or item.get("gene") or []
    return [entry for entry in genes if isinstance(entry, dict)]


def _flatten_assay_list(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        for key in ("name", "description"):
            text = entry.get(key)
            if text:
                parts.append(str(text))
    return " ".join(parts)


def _parse_activity_summary(value: Any) -> tuple[int | None, int | None]:
    if value is None or value == "":
        return None, None
    if isinstance(value, int):
        return value, None

    match = re.search(r"(\d+)\s*/\s*(\d+)", str(value))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


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


def _phrase_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for token in _normalize_catalog_text(value).split():
        if len(token) < 5:
            continue
        if token in {"liver", "hepatic", "assay", "activity", "response", "cell", "cells"}:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _score_phrase_match(
    *,
    phrase: str,
    assay_name: str | None,
    endpoint_name: str | None,
    item_text: str,
    item_gene_names: set[str],
) -> tuple[int, set[str], set[str]]:
    score = 0
    match_basis: set[str] = set()
    matched_terms: set[str] = set()
    assay_name_norm = _normalize_catalog_text(assay_name)
    endpoint_name_norm = _normalize_catalog_text(endpoint_name)

    if phrase in item_gene_names:
        score += 90
        matched_terms.add(phrase)
        match_basis.add("gene_name_exact")
    if assay_name_norm and phrase in assay_name_norm:
        score += 55
        matched_terms.add(phrase)
        match_basis.add("assay_name_phrase")
    elif endpoint_name_norm and phrase in endpoint_name_norm:
        score += 55
        matched_terms.add(phrase)
        match_basis.add("assay_endpoint_phrase")
    elif phrase in item_text:
        score += 25
        matched_terms.add(phrase)
        match_basis.add("assay_description_phrase")

    if score > 0:
        return score, match_basis, matched_terms

    for token in _phrase_tokens(phrase):
        if assay_name_norm and token in assay_name_norm:
            score += 20
            matched_terms.add(token)
            match_basis.add("assay_name_token")
        elif endpoint_name_norm and token in endpoint_name_norm:
            score += 20
            matched_terms.add(token)
            match_basis.add("assay_endpoint_token")
        elif token in item_text:
            score += 10
            matched_terms.add(token)
            match_basis.add("assay_description_token")

    return score, match_basis, matched_terms
