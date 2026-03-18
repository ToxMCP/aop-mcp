"""AOP-DB SPARQL adapter for chemical and assay mappings."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .aop_wiki import _iri_to_curie  # reuse IRI normalization
from .comp_tox import CompToxClient, CompToxError
from .fixtures import FixtureNotFoundError, load_fixture
from .sparql_client import SparqlClient, SparqlClientError
from .sparql_client import TemplateCatalog as _TemplateCatalog

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "aop_db"

_KEY_EVENT_SYMBOL_STOPWORDS = {
    "ACTIVATION",
    "ACTIVITY",
    "ADVERSE",
    "ALTERED",
    "CHANGE",
    "DECREASE",
    "DECREASED",
    "DECREASES",
    "DECREASING",
    "EVENT",
    "EXPRESSION",
    "INCREASE",
    "INCREASED",
    "INCREASES",
    "INCREASING",
    "INDUCTION",
    "LIVER",
    "MOLECULAR",
    "OUTCOME",
    "RECEPTOR",
    "REPRESSION",
    "RESPONSE",
    "STEATOSIS",
}

_KEY_EVENT_PHRASE_STOPWORDS = {
    "a",
    "accumulation",
    "activation",
    "activated",
    "activates",
    "activity",
    "adverse",
    "altered",
    "and",
    "change",
    "changes",
    "decrease",
    "decreased",
    "decreases",
    "decreasing",
    "event",
    "events",
    "elevated",
    "enhanced",
    "expression",
    "induced",
    "inhibited",
    "in",
    "increase",
    "increased",
    "increases",
    "increasing",
    "induction",
    "lead",
    "leads",
    "level",
    "levels",
    "mediated",
    "of",
    "persistent",
    "protein",
    "response",
    "repression",
    "repressed",
    "reduced",
    "serum",
    "sustained",
    "suppressed",
    "the",
    "to",
    "upregulated",
    "upregulation",
    "via",
    "downregulated",
    "downregulation",
}

_GENE_SYMBOL_NORMALIZATION = {
    "NR1L2": "NR1I2",
}

_TAXON_PREFERENCE_MAP = {
    "NCBITaxon:9606": ["human", "homo sapiens"],
    "NCBITaxon:10090": ["mouse", "mus musculus"],
    "NCBITaxon:10116": ["rat", "rattus norvegicus"],
}

_PHENOTYPE_PHRASE_EXPANSIONS = {
    "triglyceride": ["steatosis"],
    "triglycerides": ["steatosis"],
    "steatosis": ["liver steatosis", "fatty liver"],
    "liver steatosis": ["steatosis", "fatty liver"],
    "fatty liver": ["steatosis", "liver steatosis"],
    "lipid accumulation": ["steatosis"],
    "neutral lipid accumulation": ["steatosis"],
}

_GENE_ALIAS_RULES = [
    {
        "patterns": [r"\bpregnane x receptor\b", r"\bpxr\b"],
        "gene_symbols": ["PXR", "NR1I2"],
        "phrases": ["pregnane x receptor"],
    },
    {
        "patterns": [r"\bfarnesoid x receptor\b", r"\bfxr\b"],
        "gene_symbols": ["FXR", "NR1H4"],
        "phrases": ["farnesoid x receptor"],
    },
    {
        "patterns": [r"\bliver x receptor\b", r"\blxr\b"],
        "gene_symbols": ["LXR", "NR1H3", "NR1H2"],
        "phrases": ["liver x receptor"],
    },
    {
        "patterns": [r"\bnrf2\b", r"\bnfe2l2\b", r"\bnfe2/nrf2\b"],
        "gene_symbols": ["NRF2", "NFE2L2"],
        "phrases": ["nrf2"],
    },
    {
        "patterns": [r"\bahr\b", r"\baryl hydrocarbon receptor\b"],
        "gene_symbols": ["AHR"],
        "phrases": ["aryl hydrocarbon receptor"],
    },
    {
        "patterns": [r"\bconstitutive androstane receptor\b", r"\bcar\b"],
        "gene_symbols": ["CAR", "NR1I3"],
        "phrases": ["constitutive androstane receptor"],
    },
]


def _aop_iri(aop_id: str) -> str:
    if aop_id.startswith("http://") or aop_id.startswith("https://"):
        return aop_id
    suffix = aop_id.split(":", 1)[1] if aop_id.upper().startswith("AOP:") else aop_id
    return f"https://identifiers.org/aop/{suffix}"


def _cas_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    prefix = "https://identifiers.org/cas/"
    if not uri.startswith(prefix):
        return None
    return uri.rsplit("/", 1)[-1]

class AOPDBAdapter:
    def __init__(
        self,
        client: SparqlClient,
        cache_ttl_seconds: int = 600,
        *,
        comptox_client: CompToxClient | None = None,
        enable_fixture_fallback: bool = True,
    ) -> None:
        self.client = client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._templates = _TemplateCatalog.from_directory(TEMPLATE_DIR)
        self.comptox = comptox_client
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
        
        # 1. Fetch chemicals active in this assay from CompTox Bioactivity API
        chemicals = []
        if self.comptox:
            try:
                chemicals = self.comptox.get_chemicals_in_assay(assay_id)
            except Exception:
                # Fallback or ignore if CompTox fails
                pass
        
        if not chemicals:
            # Fallback to legacy AOP-DB query if no chemicals found or no CompTox client
            # (This will likely return empty list if AOP-DB is down)
            return await self._map_assay_legacy(assay_id)

        # 2. For each chemical, map to AOPs using AOP-Wiki
        results: list[dict[str, Any]] = []
        # Limit to top 5 chemicals to avoid spamming AOP-Wiki in one go if assay has hundreds of hits
        # Ideally, we'd batch this or use a more efficient query.
        for chem in chemicals[:5]:
            # Prefer DTXSID, CAS, Name
            # The bioactivity payload structure depends on the API response.
            # Based on mcp_epacomp_tox code, result objects have identifiers.
            dtxsid = chem.get("dtxsid")
            name = chem.get("preferredName") or chem.get("name")
            cas = chem.get("casrn")

            # Construct query params for map_chemical_to_aops
            # map_chemical_to_aops expects name or cas or inchikey.
            # It handles name and cas in the SPARQL template.
            if name or cas:
                try:
                    chem_aops = await self.map_chemical_to_aops(name=name, cas=cas)
                    for ca in chem_aops:
                        # Add assay context to the result
                        ca["assay_id"] = assay_id
                        ca["chemical_context"] = {"dtxsid": dtxsid, "name": name}
                        results.append(ca)
                except Exception:
                    continue
        
        return results

    async def list_assays_for_aop(
        self,
        aop_id: str,
        *,
        limit: int = 25,
        min_hitcall: float = 0.9,
    ) -> list[dict[str, Any]]:
        if not aop_id:
            raise ValueError("aop_id is required")
        if not self.comptox or not self.comptox.has_api_key:
            raise ValueError("CompTox API key is required for AOP assay candidate lookup")

        stressors = await self._list_stressor_chemicals_for_aop(aop_id)
        if not stressors:
            return []

        assay_candidates: dict[int, dict[str, Any]] = {}
        for stressor in stressors[:10]:
            search_value = stressor["casrn"] or stressor["label"]
            if not search_value:
                continue

            chemical_matches = self.comptox.search_equal(search_value)
            if not chemical_matches:
                continue
            chemical = chemical_matches[0]
            dtxsid = chemical.get("dtxsid")
            if not dtxsid:
                continue

            best_hits_by_aeid: dict[int, dict[str, Any]] = {}
            for hit in self.comptox.bioactivity_data_by_dtxsid(dtxsid):
                aeid = hit.get("aeid")
                hitcall = float(hit.get("hitc") or 0.0)
                if aeid is None or hitcall < min_hitcall:
                    continue
                aeid_int = int(aeid)
                current = best_hits_by_aeid.get(aeid_int)
                if current is None or hitcall > float(current.get("hitc") or 0.0):
                    best_hits_by_aeid[aeid_int] = hit

            ranked_hits = sorted(
                best_hits_by_aeid.values(),
                key=lambda item: (float(item.get("hitc") or 0.0), -float(item.get("coff") or 1e9)),
                reverse=True,
            )[: min(limit, 15)]

            for hit in ranked_hits:
                aeid = int(hit["aeid"])
                candidate = assay_candidates.setdefault(
                    aeid,
                    {
                        "aeid": aeid,
                        "assay_name": None,
                        "assay_component_endpoint_name": None,
                        "assay_component_endpoint_desc": None,
                        "assay_function_type": None,
                        "target_family": None,
                        "target_family_sub": None,
                        "gene_symbols": [],
                        "support_count": 0,
                        "max_hitcall": 0.0,
                        "supporting_chemicals": [],
                        "_seen_dtxsids": set(),
                    },
                )
                if dtxsid in candidate["_seen_dtxsids"]:
                    continue
                candidate["_seen_dtxsids"].add(dtxsid)
                candidate["support_count"] += 1
                candidate["max_hitcall"] = max(candidate["max_hitcall"], float(hit.get("hitc") or 0.0))
                candidate["supporting_chemicals"].append(
                    {
                        "dtxsid": dtxsid,
                        "casrn": chemical.get("casrn") or stressor["casrn"],
                        "preferred_name": chemical.get("preferredName") or stressor["label"],
                        "stressor_id": stressor["stressor_id"],
                        "stressor_label": stressor["label"],
                        "hitcall": float(hit.get("hitc") or 0.0),
                        "activity_cutoff": hit.get("coff"),
                    }
                )

        ranked_candidates = sorted(
            assay_candidates.values(),
            key=lambda item: (item["support_count"], item["max_hitcall"], -(item["aeid"])),
            reverse=True,
        )[:limit]

        for candidate in ranked_candidates:
            assay = self.comptox.assay_by_aeid(candidate["aeid"]) or {}
            genes = assay.get("gene") or []
            candidate["assay_name"] = assay.get("assayName")
            candidate["assay_component_endpoint_name"] = assay.get("assayComponentEndpointName")
            candidate["assay_component_endpoint_desc"] = assay.get("assayComponentEndpointDesc")
            candidate["assay_function_type"] = assay.get("assayFunctionType")
            candidate["target_family"] = assay.get("intendedTargetFamily")
            candidate["target_family_sub"] = assay.get("intendedTargetFamilySub")
            candidate["gene_symbols"] = sorted(
                {gene.get("geneSymbol") for gene in genes if gene.get("geneSymbol")}
            )
            candidate.pop("_seen_dtxsids", None)

        return ranked_candidates

    async def list_assays_for_aops(
        self,
        aop_ids: list[str],
        *,
        limit: int = 25,
        per_aop_limit: int = 15,
        min_hitcall: float = 0.9,
    ) -> list[dict[str, Any]]:
        normalized_aop_ids = list(dict.fromkeys(aop_ids))
        if not normalized_aop_ids:
            raise ValueError("At least one aop_id is required")

        aggregated_candidates: dict[int, dict[str, Any]] = {}
        for aop_id in normalized_aop_ids:
            assay_rows = await self.list_assays_for_aop(
                aop_id,
                limit=per_aop_limit,
                min_hitcall=min_hitcall,
            )
            for row in assay_rows:
                aeid = row["aeid"]
                candidate = aggregated_candidates.setdefault(
                    aeid,
                    {
                        "aeid": aeid,
                        "assay_name": row.get("assay_name"),
                        "assay_component_endpoint_name": row.get("assay_component_endpoint_name"),
                        "assay_component_endpoint_desc": row.get("assay_component_endpoint_desc"),
                        "assay_function_type": row.get("assay_function_type"),
                        "target_family": row.get("target_family"),
                        "target_family_sub": row.get("target_family_sub"),
                        "gene_symbols": set(row.get("gene_symbols", [])),
                        "max_hitcall": float(row.get("max_hitcall") or 0.0),
                        "_supporting_aops": set(),
                        "_supporting_chemicals": {},
                    },
                )
                candidate["_supporting_aops"].add(aop_id)
                candidate["max_hitcall"] = max(candidate["max_hitcall"], float(row.get("max_hitcall") or 0.0))
                candidate["gene_symbols"].update(row.get("gene_symbols", []))

                supporting_chemicals: dict[str, dict[str, Any]] = candidate["_supporting_chemicals"]
                for chemical in row.get("supporting_chemicals", []):
                    chemical_key = chemical.get("dtxsid") or chemical.get("casrn") or chemical.get("preferred_name")
                    if not chemical_key:
                        continue
                    aggregated_chemical = supporting_chemicals.setdefault(
                        chemical_key,
                        {
                            "dtxsid": chemical.get("dtxsid"),
                            "casrn": chemical.get("casrn"),
                            "preferred_name": chemical.get("preferred_name"),
                            "max_hitcall": float(chemical.get("hitcall") or 0.0),
                            "best_activity_cutoff": chemical.get("activity_cutoff"),
                            "_aop_ids": set(),
                            "_stressor_ids": set(),
                            "_stressor_labels": set(),
                        },
                    )
                    aggregated_chemical["max_hitcall"] = max(
                        aggregated_chemical["max_hitcall"],
                        float(chemical.get("hitcall") or 0.0),
                    )
                    activity_cutoff = chemical.get("activity_cutoff")
                    if activity_cutoff is not None:
                        current_cutoff = aggregated_chemical.get("best_activity_cutoff")
                        if current_cutoff is None or activity_cutoff < current_cutoff:
                            aggregated_chemical["best_activity_cutoff"] = activity_cutoff
                    aggregated_chemical["_aop_ids"].add(aop_id)
                    if chemical.get("stressor_id"):
                        aggregated_chemical["_stressor_ids"].add(chemical["stressor_id"])
                    if chemical.get("stressor_label"):
                        aggregated_chemical["_stressor_labels"].add(chemical["stressor_label"])

        materialized_candidates: list[dict[str, Any]] = []
        for candidate in aggregated_candidates.values():
            supporting_aops = sorted(candidate.pop("_supporting_aops"))
            supporting_chemicals: list[dict[str, Any]] = []
            for chemical in candidate.pop("_supporting_chemicals").values():
                supporting_chemicals.append(
                    {
                        "dtxsid": chemical.get("dtxsid"),
                        "casrn": chemical.get("casrn"),
                        "preferred_name": chemical.get("preferred_name"),
                        "max_hitcall": chemical.get("max_hitcall"),
                        "best_activity_cutoff": chemical.get("best_activity_cutoff"),
                        "aop_ids": sorted(chemical.pop("_aop_ids")),
                        "stressor_ids": sorted(chemical.pop("_stressor_ids")),
                        "stressor_labels": sorted(chemical.pop("_stressor_labels")),
                    }
                )

            supporting_chemicals.sort(
                key=lambda item: (-len(item["aop_ids"]), -float(item.get("max_hitcall") or 0.0), item.get("preferred_name") or "")
            )
            candidate["gene_symbols"] = sorted(candidate["gene_symbols"])
            candidate["supporting_aops"] = supporting_aops
            candidate["aop_support_count"] = len(supporting_aops)
            candidate["supporting_chemicals"] = supporting_chemicals
            candidate["chemical_support_count"] = len(supporting_chemicals)
            materialized_candidates.append(candidate)

        materialized_candidates.sort(
            key=lambda item: (
                -item["aop_support_count"],
                -item["chemical_support_count"],
                -float(item.get("max_hitcall") or 0.0),
                item["aeid"],
            )
        )
        return materialized_candidates[:limit]

    async def search_assays_for_key_event(
        self,
        key_event: dict[str, Any],
        *,
        limit: int = 25,
    ) -> dict[str, Any]:
        if not self.comptox:
            raise ValueError("CompTox client is required for key-event assay search")

        derived_search_terms = _derive_key_event_search_terms(key_event)
        limitations = [
            "Assays are ranked using key-event-derived gene and phrase matches against CompTox assay search endpoints when available, with catalog and AOP-Wiki measurement-method fallbacks; this is not a curated KE-to-assay ontology mapping.",
        ]

        if not derived_search_terms["gene_symbols"] and not derived_search_terms["phrases"]:
            limitations.append(
                "No gene-like symbols or searchable phrases could be derived from the key event metadata."
            )
            return {
                "derived_search_terms": derived_search_terms,
                "limitations": limitations,
                "results": [],
            }

        if not derived_search_terms["gene_symbols"]:
            limitations.append(
                "This key event did not expose gene-like symbols, so assay matching relies on phrase similarity and may be broader."
            )

        used_measurement_fallback = False
        try:
            results = self.comptox.search_assay_catalog(
                gene_symbols=derived_search_terms["gene_symbols"],
                phrases=derived_search_terms["phrases"],
                preferred_taxa=_preferred_taxa_from_key_event(key_event),
                limit=limit,
            )
        except CompToxError as exc:
            used_measurement_fallback = True
            limitations.append(
                "CompTox assay search was unavailable or unauthorized, so results were derived from AOP-Wiki measurement-method text instead."
            )
            limitations.append(f"CompTox detail: {exc}")
            results = _extract_measurement_method_assays(
                key_event.get("measurement_methods") or [],
                gene_symbols=derived_search_terms["gene_symbols"],
                limit=limit,
            )
        if not results and key_event.get("measurement_methods") and not used_measurement_fallback:
            used_measurement_fallback = True
            limitations.append(
                "No CompTox assay candidates matched the derived key-event terms, so AOP-Wiki measurement-method text was used as a fallback."
            )
            results = _extract_measurement_method_assays(
                key_event.get("measurement_methods") or [],
                gene_symbols=derived_search_terms["gene_symbols"],
                limit=limit,
            )
        if not results:
            if used_measurement_fallback:
                limitations.append(
                    "No assay candidates were recovered from CompTox assay search or AOP-Wiki measurement-method text."
                )
            else:
                limitations.append("No CompTox assay candidates matched the derived key-event terms.")

        return {
            "derived_search_terms": derived_search_terms,
            "limitations": limitations,
            "results": results,
        }

    async def _map_assay_legacy(self, assay_id: str) -> list[dict[str, Any]]:
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

    async def _list_stressor_chemicals_for_aop(self, aop_id: str) -> list[dict[str, Any]]:
        query = self._templates.render("list_stressor_chemicals_for_aop", {"aop_iri": _aop_iri(aop_id)})
        payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        bindings = payload.get("results", {}).get("bindings", [])
        stressors: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str | None, str | None]] = set()
        for row in bindings:
            stressor_id = row.get("stressor", {}).get("value")
            chemical_iri = row.get("chemicalEntity", {}).get("value")
            dedupe_key = (stressor_id, chemical_iri)
            if dedupe_key in seen_pairs:
                continue
            seen_pairs.add(dedupe_key)
            stressors.append(
                {
                    "stressor_id": stressor_id,
                    "label": row.get("stressorLabel", {}).get("value"),
                    "chemical_iri": chemical_iri,
                    "casrn": _cas_from_uri(chemical_iri),
                }
            )
        return stressors


def _derive_key_event_search_terms(key_event: dict[str, Any]) -> dict[str, list[str]]:
    title = str(key_event.get("title") or "")
    short_name = str(key_event.get("short_name") or "")
    description = str(key_event.get("description") or "")
    label_source = " ".join(filter(None, [title, short_name]))

    gene_symbols: list[str] = []
    for value in (title, short_name):
        for token in re.split(r"[^A-Za-z0-9/+_-]+", value):
            for part in re.split(r"[+/]", token):
                symbol = _normalize_gene_like_token(part)
                if symbol and symbol not in gene_symbols:
                    gene_symbols.append(symbol)

    phrases: list[str] = []
    for value in (title, short_name):
        for segment in re.split(r"[,;()]+", value):
            phrase = _normalize_key_event_phrase(segment, gene_symbols=gene_symbols)
            if phrase and phrase not in phrases:
                phrases.append(phrase)

    _expand_alias_terms(label_source, gene_symbols, phrases)
    if not gene_symbols and not phrases:
        for symbol in _extract_description_gene_symbols(description):
            if symbol not in gene_symbols:
                gene_symbols.append(symbol)
        _expand_alias_terms(description, gene_symbols, phrases)
    gene_symbols = _finalize_gene_symbols(gene_symbols)
    if not gene_symbols:
        phrases = _expand_phenotype_phrases(phrases)
    phrases = _finalize_phrases(phrases, gene_symbols)

    return {
        "gene_symbols": gene_symbols[:8],
        "phrases": phrases[:8],
    }


def _normalize_gene_like_token(value: str) -> str | None:
    token = value.strip().strip("-_")
    if len(token) < 3:
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", token):
        return None

    upper = _GENE_SYMBOL_NORMALIZATION.get(token.upper(), token.upper())
    if upper in _KEY_EVENT_SYMBOL_STOPWORDS:
        return None
    if not any(char.isdigit() for char in token) and not token.isupper():
        return None
    return upper


def _normalize_key_event_phrase(value: str, *, gene_symbols: list[str]) -> str | None:
    if not value:
        return None
    normalized = value.replace("-", " ").replace("/", " ")
    normalized = re.sub(r"[^A-Za-z0-9\s]", " ", normalized).lower()
    tokens = []
    for token in normalized.split():
        if token in _KEY_EVENT_PHRASE_STOPWORDS:
            continue
        canonical_symbol = _normalize_gene_like_token(token)
        if token.upper() in gene_symbols or (canonical_symbol and canonical_symbol in gene_symbols):
            continue
        tokens.append(token)

    if not tokens:
        return None
    phrase = " ".join(tokens).strip()
    return phrase if len(phrase) >= 3 else None


def _extract_description_gene_symbols(value: str) -> list[str]:
    symbols: list[str] = []
    for section in re.findall(r"\(([^)]+)\)", value or ""):
        for token in re.split(r"[^A-Za-z0-9/+_-]+", section):
            for part in re.split(r"[+/]", token):
                symbol = _normalize_gene_like_token(part)
                if symbol and symbol not in symbols:
                    symbols.append(symbol)
    return symbols


def _expand_alias_terms(source_text: str, gene_symbols: list[str], phrases: list[str]) -> None:
    normalized = re.sub(r"[-_/]+", " ", source_text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for rule in _GENE_ALIAS_RULES:
        if not any(re.search(pattern, normalized) for pattern in rule["patterns"]):
            continue
        for symbol in rule["gene_symbols"]:
            if symbol not in gene_symbols:
                gene_symbols.append(symbol)
        for phrase in rule["phrases"]:
            if phrase not in phrases:
                phrases.append(phrase)


def _finalize_gene_symbols(gene_symbols: list[str]) -> list[str]:
    deduped: list[str] = []
    for symbol in gene_symbols:
        canonical = _GENE_SYMBOL_NORMALIZATION.get(symbol, symbol)
        if canonical not in deduped:
            deduped.append(canonical)

    if "NFE2L2" in deduped and "NFE2" in deduped:
        deduped = [symbol for symbol in deduped if symbol != "NFE2"]
    if "NR1I2" in deduped and "NR1L2" in deduped:
        deduped = [symbol for symbol in deduped if symbol != "NR1L2"]
    return deduped


def _finalize_phrases(phrases: list[str], gene_symbols: list[str]) -> list[str]:
    deduped: list[str] = []
    for phrase in phrases:
        normalized = phrase.strip().lower()
        if not normalized:
            continue
        if " " not in normalized:
            canonical = _GENE_SYMBOL_NORMALIZATION.get(normalized.upper(), normalized.upper())
            if canonical in gene_symbols:
                continue
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _expand_phenotype_phrases(phrases: list[str]) -> list[str]:
    expanded = list(phrases)
    for phrase in phrases:
        normalized = phrase.strip().lower()
        for synonym in _PHENOTYPE_PHRASE_EXPANSIONS.get(normalized, []):
            if synonym not in expanded:
                expanded.append(synonym)
    return expanded


def _preferred_taxa_from_key_event(key_event: dict[str, Any]) -> list[str]:
    preferred_taxa: list[str] = []
    for taxon in key_event.get("taxonomic_applicability") or []:
        for label in _TAXON_PREFERENCE_MAP.get(taxon, []):
            if label not in preferred_taxa:
                preferred_taxa.append(label)
    return preferred_taxa


def _extract_measurement_method_assays(
    measurement_methods: list[str],
    *,
    gene_symbols: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    assay_names: list[str] = []
    for text in measurement_methods:
        for match in re.findall(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+){1,}\b", text):
            assay_name = match.strip(".,;:()[]")
            if assay_name and assay_name not in assay_names:
                assay_names.append(assay_name)

    return [
        {
            "aeid": None,
            "assay_name": assay_name,
            "assay_component_endpoint_name": assay_name,
            "assay_component_endpoint_desc": "Recovered from AOP-Wiki key event measurement methods.",
            "assay_function_type": None,
            "target_family": None,
            "target_family_sub": None,
            "target_type": None,
            "gene_symbols": gene_symbols,
            "taxon_name": None,
            "applicability_match": "unknown",
            "matched_taxa": [],
            "match_score": 40,
            "match_basis": ["key_event_measurement_methods"],
            "matched_terms": [assay_name],
            "multi_conc_assay_chemical_count_active": None,
            "multi_conc_assay_chemical_count_total": None,
            "single_conc_assay_chemical_count_active": None,
            "single_conc_assay_chemical_count_total": None,
            "source": "aop_wiki_measurement_methods",
        }
        for assay_name in assay_names[:limit]
    ]
