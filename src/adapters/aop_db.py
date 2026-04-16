"""AOP-DB SPARQL adapter for chemical and assay mappings."""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

from src.semantic import AOP_CURIE_RESOLVER
from .comp_tox import CompToxClient, CompToxError, compute_specificity_score
from .fixtures import FixtureNotFoundError, load_fixture
from .hgnc import HgncClient, HgncError
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

_ASSAY_EMPTY_REASON_MISSING_COMPTOX_API_KEY = "missing_comptox_api_key"
_ASSAY_EMPTY_REASON_NO_LINKED_STRESSORS = "no_linked_stressors"
_ASSAY_EMPTY_REASON_NO_COMPTOX_CHEMICAL_MATCH = "no_comptox_chemical_match"
_ASSAY_EMPTY_REASON_NO_BIOACTIVITY_HITS = "no_bioactivity_hits_after_filtering"
_ORPHAN_EMPTY_REASON_NO_ASSAY_CANDIDATES = "no_assay_candidates"
_ORPHAN_EMPTY_REASON_NO_ASSAY_CHEMICAL_HITS = "no_assay_chemical_hits"
_ORPHAN_EMPTY_REASON_NO_ORPHAN_CANDIDATES = "no_orphan_candidates_after_excluding_curated_chemicals"

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
        hgnc_client: HgncClient | None = None,
        enable_fixture_fallback: bool = True,
        comptox_concurrency_limit: int = 8,
    ) -> None:
        self.client = client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._templates = _TemplateCatalog.from_directory(TEMPLATE_DIR)
        self.comptox = comptox_client
        self.hgnc = hgnc_client
        self.enable_fixture_fallback = enable_fixture_fallback
        self.comptox_concurrency_limit = max(1, comptox_concurrency_limit)

    async def map_chemical_to_aops(
        self,
        *,
        cas: str | None = None,
        name: str | None = None,
    ) -> list[dict[str, Any]]:
        if not any([cas, name]):
            raise ValueError("At least one identifier (cas, name) must be provided")

        cas_uri = f"https://identifiers.org/cas/{quote(cas, safe='')}" if cas else ""
        query = self._templates.render_safe(
            "map_chemical_to_aops",
            literals={
                "name": name or "",
                "cas_literal": cas or "",
            },
            uris={"cas_uri": cas_uri},
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
                        "id": AOP_CURIE_RESOLVER.resolve(aop.get("value", "")),
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
                chemicals = await self._call_comptox("get_chemicals_in_assay", assay_id)
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
        results, _diagnostics = await self._list_assays_for_aop_with_diagnostics(
            aop_id,
            limit=limit,
            min_hitcall=min_hitcall,
        )
        return results

    async def list_assays_for_aop_with_diagnostics(
        self,
        aop_id: str,
        *,
        limit: int = 25,
        min_hitcall: float = 0.9,
    ) -> dict[str, Any]:
        results, diagnostics = await self._list_assays_for_aop_with_diagnostics(
            aop_id,
            limit=limit,
            min_hitcall=min_hitcall,
        )
        return {"results": results, "diagnostics": diagnostics}

    async def _list_assays_for_aop_with_diagnostics(
        self,
        aop_id: str,
        *,
        limit: int = 25,
        min_hitcall: float = 0.9,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not aop_id:
            raise ValueError("aop_id is required")
        diagnostics = {
            "aop_id": aop_id,
            "comptox_api_key_configured": bool(self.comptox and self.comptox.has_api_key),
            "stressor_count": 0,
            "chemical_match_count": 0,
            "bioactivity_hit_count": 0,
            "returned_assay_count": 0,
            "empty_reason": None,
            "warnings": [],
        }
        if not self.comptox or not self.comptox.has_api_key:
            diagnostics["empty_reason"] = _ASSAY_EMPTY_REASON_MISSING_COMPTOX_API_KEY
            diagnostics["warnings"].append(
                "CompTox API key is not configured; use AOP identifiers with get_assays_for_aop or get_assays_for_aops only after CompTox access is available."
            )
            return [], diagnostics

        stressors = await self._list_stressor_chemicals_for_aop(aop_id)
        diagnostics["stressor_count"] = len(stressors)
        if not stressors:
            diagnostics["empty_reason"] = _ASSAY_EMPTY_REASON_NO_LINKED_STRESSORS
            diagnostics["warnings"].append(
                "No linked stressor chemicals were found for this AOP in AOP-DB."
            )
            return [], diagnostics

        assay_candidates: dict[int, dict[str, Any]] = {}
        matched_dtxsids: set[str] = set()
        missing_search_value_count = 0
        for stressor in stressors[:10]:
            search_value = stressor["casrn"] or stressor["label"]
            if not search_value:
                missing_search_value_count += 1
                continue

            chemical_matches = await self._call_comptox("search_equal", search_value)
            if not chemical_matches:
                continue
            chemical = chemical_matches[0]
            dtxsid = chemical.get("dtxsid")
            if not dtxsid:
                continue
            matched_dtxsids.add(dtxsid)

            best_hits_by_aeid: dict[int, dict[str, Any]] = {}
            for hit in await self._call_comptox("bioactivity_data_by_dtxsid", dtxsid):
                aeid = hit.get("aeid")
                hitcall = float(hit.get("hitc") or 0.0)
                if aeid is None or hitcall < min_hitcall:
                    continue
                diagnostics["bioactivity_hit_count"] += 1
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

        diagnostics["chemical_match_count"] = len(matched_dtxsids)
        if missing_search_value_count:
            diagnostics["warnings"].append(
                "Some linked stressors lacked a searchable CAS RN or label and were skipped."
            )

        metadata_tasks = [
            self._call_comptox("assay_by_aeid", candidate["aeid"])
            for candidate in assay_candidates.values()
        ]
        metadata_results = await asyncio.gather(*metadata_tasks)
        for candidate, assay in zip(assay_candidates.values(), metadata_results):
            assay = assay or {}
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
            candidate["specificity_score"] = _assay_specificity_score(assay)
            candidate["_weighted_hitcall"] = _weighted_hitcall(
                candidate["max_hitcall"],
                candidate["specificity_score"],
            )
            candidate.pop("_seen_dtxsids", None)

        ranked_candidates = sorted(
            assay_candidates.values(),
            key=lambda item: (
                -item["support_count"],
                -float(item["_weighted_hitcall"]),
                -float(item["max_hitcall"]),
                item["aeid"],
            ),
        )[:limit]
        for candidate in ranked_candidates:
            candidate.pop("_weighted_hitcall", None)

        diagnostics["returned_assay_count"] = len(ranked_candidates)
        if diagnostics["returned_assay_count"] == 0:
            if diagnostics["chemical_match_count"] == 0:
                diagnostics["empty_reason"] = _ASSAY_EMPTY_REASON_NO_COMPTOX_CHEMICAL_MATCH
                diagnostics["warnings"].append(
                    "No CompTox chemical matches were found for the linked stressors."
                )
            elif diagnostics["bioactivity_hit_count"] == 0:
                diagnostics["empty_reason"] = _ASSAY_EMPTY_REASON_NO_BIOACTIVITY_HITS
                diagnostics["warnings"].append(
                    "CompTox chemical matches were found, but no bioactivity hits met the min_hitcall filter."
                )
        return ranked_candidates, diagnostics

    async def list_assays_for_aops(
        self,
        aop_ids: list[str],
        *,
        limit: int = 25,
        per_aop_limit: int = 15,
        min_hitcall: float = 0.9,
    ) -> list[dict[str, Any]]:
        report = await self.list_assays_for_aops_with_diagnostics(
            aop_ids,
            limit=limit,
            per_aop_limit=per_aop_limit,
            min_hitcall=min_hitcall,
        )
        return report["results"]

    async def list_assays_for_aops_with_diagnostics(
        self,
        aop_ids: list[str],
        *,
        limit: int = 25,
        per_aop_limit: int = 15,
        min_hitcall: float = 0.9,
    ) -> dict[str, Any]:
        normalized_aop_ids = list(dict.fromkeys(aop_ids))
        if not normalized_aop_ids:
            raise ValueError("At least one aop_id is required")

        aggregated_candidates: dict[int, dict[str, Any]] = {}
        per_aop_diagnostics: list[dict[str, Any]] = []
        for aop_id in normalized_aop_ids:
            assay_rows, aop_diagnostics = await self._list_assays_for_aop_with_diagnostics(
                aop_id,
                limit=per_aop_limit,
                min_hitcall=min_hitcall,
            )
            per_aop_diagnostics.append(aop_diagnostics)
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
                        "specificity_score": row.get("specificity_score"),
                        "_supporting_aops": set(),
                        "_supporting_chemicals": {},
                    },
                )
                candidate["_supporting_aops"].add(aop_id)
                candidate["max_hitcall"] = max(candidate["max_hitcall"], float(row.get("max_hitcall") or 0.0))
                candidate["gene_symbols"].update(row.get("gene_symbols", []))
                if candidate["specificity_score"] is None:
                    candidate["specificity_score"] = row.get("specificity_score")

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
            candidate["_weighted_hitcall"] = _weighted_hitcall(
                candidate["max_hitcall"],
                candidate["specificity_score"],
            )
            materialized_candidates.append(candidate)

        materialized_candidates.sort(
            key=lambda item: (
                -item["aop_support_count"],
                -item["chemical_support_count"],
                -float(item.get("_weighted_hitcall") or 0.0),
                -float(item.get("max_hitcall") or 0.0),
                item["aeid"],
            )
        )
        results = materialized_candidates[:limit]
        for candidate in results:
            candidate.pop("_weighted_hitcall", None)

        warnings: list[str] = []
        if len(normalized_aop_ids) != len(aop_ids):
            warnings.append("Duplicate AOP identifiers were deduplicated before aggregation.")
        if any(item["empty_reason"] is not None for item in per_aop_diagnostics):
            warnings.append(
                "One or more AOPs returned no assay candidates; inspect diagnostics.per_aop for details."
            )

        return {
            "results": results,
            "diagnostics": {
                "requested_aop_ids": list(aop_ids),
                "processed_aop_ids": normalized_aop_ids,
                "returned_assay_count": len(results),
                "per_aop": per_aop_diagnostics,
                "warnings": warnings,
            },
        }

    async def discover_orphan_stressors_for_aop_with_diagnostics(
        self,
        aop_id: str,
        *,
        assay_limit: int = 10,
        per_assay_chemical_limit: int = 25,
        limit: int = 25,
        min_hitcall: float = 0.9,
    ) -> dict[str, Any]:
        if not aop_id:
            raise ValueError("aop_id is required")
        diagnostics = {
            "aop_id": aop_id,
            "comptox_api_key_configured": bool(self.comptox and self.comptox.has_api_key),
            "curated_stressor_count": 0,
            "curated_chemical_match_count": 0,
            "assay_candidate_count": 0,
            "scanned_assay_count": 0,
            "assay_chemical_hit_count": 0,
            "returned_candidate_count": 0,
            "empty_reason": None,
            "warnings": [],
        }
        if not self.comptox or not self.comptox.has_api_key:
            diagnostics["empty_reason"] = _ASSAY_EMPTY_REASON_MISSING_COMPTOX_API_KEY
            diagnostics["warnings"].append(
                "CompTox API key is not configured; orphan stressor discovery requires CompTox assay-chemical lookup."
            )
            return {"results": [], "diagnostics": diagnostics}

        stressors = await self._list_stressor_chemicals_for_aop(aop_id)
        diagnostics["curated_stressor_count"] = len(stressors)
        if not stressors:
            diagnostics["empty_reason"] = _ASSAY_EMPTY_REASON_NO_LINKED_STRESSORS
            diagnostics["warnings"].append(
                "No linked stressor chemicals were found for this AOP in AOP-DB."
            )
            return {"results": [], "diagnostics": diagnostics}

        curated_index, curated_match_count, curated_warnings = await self._build_curated_chemical_index(stressors)
        diagnostics["curated_chemical_match_count"] = curated_match_count
        diagnostics["warnings"].extend(curated_warnings)

        assay_report = await self.list_assays_for_aop_with_diagnostics(
            aop_id,
            limit=assay_limit,
            min_hitcall=min_hitcall,
        )
        assay_rows = assay_report["results"]
        assay_diagnostics = assay_report["diagnostics"]
        diagnostics["assay_candidate_count"] = len(assay_rows)
        diagnostics["warnings"].extend(assay_diagnostics["warnings"])
        if not assay_rows:
            diagnostics["empty_reason"] = (
                assay_diagnostics.get("empty_reason") or _ORPHAN_EMPTY_REASON_NO_ASSAY_CANDIDATES
            )
            diagnostics["warnings"] = list(dict.fromkeys(diagnostics["warnings"]))
            return {"results": [], "diagnostics": diagnostics}

        scanned_assays = self._rank_assays_for_orphan_scanning(assay_rows)[:assay_limit]
        diagnostics["scanned_assay_count"] = len(scanned_assays)
        assay_chemical_results = await self._gather_bounded(
            [
                self._fetch_orphan_assay_chemicals(assay_row["aeid"])
                for assay_row in scanned_assays
            ],
            limit=self.comptox_concurrency_limit,
            return_exceptions=True,
        )

        orphan_candidates: dict[str, dict[str, Any]] = {}
        candidate_aliases: dict[str, str] = {}
        for assay_rank, (assay_row, assay_chemicals) in enumerate(
            zip(scanned_assays, assay_chemical_results, strict=False),
            start=1,
        ):
            if isinstance(assay_chemicals, Exception):
                diagnostics["warnings"].append(
                    f"CompTox assay-chemical lookup failed for AEID {assay_row['aeid']}: {assay_chemicals}"
                )
                continue

            for chemical in assay_chemicals[:per_assay_chemical_limit]:
                diagnostics["assay_chemical_hit_count"] += 1
                normalized_chemical = _normalize_assay_chemical_record(chemical)
                if not _chemical_identity_available(normalized_chemical):
                    continue
                if _chemical_matches_index(normalized_chemical, curated_index):
                    continue

                candidate_key = next(
                    (
                        candidate_aliases[alias]
                        for alias in _chemical_alias_keys(normalized_chemical)
                        if alias in candidate_aliases
                    ),
                    None,
                ) or _chemical_candidate_key(normalized_chemical)
                if candidate_key is None:
                    continue
                candidate = orphan_candidates.setdefault(
                    candidate_key,
                    {
                        "dtxsid": normalized_chemical.get("dtxsid"),
                        "casrn": normalized_chemical.get("casrn"),
                        "preferred_name": normalized_chemical.get("preferred_name"),
                        "supporting_assay_count": 0,
                        "best_assay_rank": assay_rank,
                        "max_specificity_score": assay_row.get("specificity_score"),
                        "supporting_assays": [],
                        "_seen_aeids": set(),
                    },
                )
                for alias in _chemical_alias_keys(normalized_chemical):
                    candidate_aliases.setdefault(alias, candidate_key)
                if candidate["dtxsid"] is None:
                    candidate["dtxsid"] = normalized_chemical.get("dtxsid")
                if candidate["casrn"] is None:
                    candidate["casrn"] = normalized_chemical.get("casrn")
                if candidate["preferred_name"] is None:
                    candidate["preferred_name"] = normalized_chemical.get("preferred_name")
                candidate["best_assay_rank"] = min(candidate["best_assay_rank"], assay_rank)

                assay_specificity = assay_row.get("specificity_score")
                if assay_specificity is not None:
                    current_specificity = candidate.get("max_specificity_score")
                    if current_specificity is None or assay_specificity > current_specificity:
                        candidate["max_specificity_score"] = assay_specificity

                aeid = assay_row["aeid"]
                if aeid in candidate["_seen_aeids"]:
                    continue
                candidate["_seen_aeids"].add(aeid)
                candidate["supporting_assay_count"] += 1
                candidate["supporting_assays"].append(
                    {
                        "aeid": aeid,
                        "assay_name": assay_row.get("assay_name"),
                        "rank": assay_rank,
                        "specificity_score": assay_specificity,
                    }
                )

        if diagnostics["assay_chemical_hit_count"] == 0:
            diagnostics["empty_reason"] = _ORPHAN_EMPTY_REASON_NO_ASSAY_CHEMICAL_HITS
            diagnostics["warnings"].append(
                "The selected assay candidates did not return any active chemicals from CompTox."
            )
            diagnostics["warnings"] = list(dict.fromkeys(diagnostics["warnings"]))
            return {"results": [], "diagnostics": diagnostics}

        ranked_candidates = sorted(
            orphan_candidates.values(),
            key=lambda item: (
                -item["supporting_assay_count"],
                item["best_assay_rank"],
                -(item["max_specificity_score"] if item["max_specificity_score"] is not None else -1.0),
                item.get("preferred_name") or "",
            ),
        )[:limit]

        for candidate in ranked_candidates:
            candidate["supporting_assays"].sort(
                key=lambda item: (
                    item["rank"],
                    -(item["specificity_score"] if item["specificity_score"] is not None else -1.0),
                    item["aeid"],
                )
            )
            candidate.pop("_seen_aeids", None)

        diagnostics["returned_candidate_count"] = len(ranked_candidates)
        if diagnostics["returned_candidate_count"] == 0:
            diagnostics["empty_reason"] = _ORPHAN_EMPTY_REASON_NO_ORPHAN_CANDIDATES
            diagnostics["warnings"].append(
                "All active assay chemicals for the selected pathway assays were already linked as curated AOP stressors or matched their known CAS/name identifiers."
            )
        diagnostics["warnings"] = list(dict.fromkeys(diagnostics["warnings"]))
        return {"results": ranked_candidates, "diagnostics": diagnostics}

    def _rank_assays_for_orphan_scanning(
        self,
        assay_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
            assay_function_type = str(item.get("assay_function_type") or "").strip().lower()
            target_family = str(item.get("target_family") or "").strip().lower()
            deprioritized = assay_function_type == "background control" or target_family == "cell morphology"
            specificity_score = item.get("specificity_score")
            return (
                deprioritized,
                -(1 if specificity_score is not None else 0),
                -float(specificity_score if specificity_score is not None else -1.0),
                -len(item.get("gene_symbols") or []),
                -int(item.get("support_count") or 0),
                -float(item.get("max_hitcall") or 0.0),
                int(item.get("aeid") or 0),
            )

        return sorted(assay_rows, key=sort_key)

    async def _fetch_orphan_assay_chemicals(self, aeid: int | str) -> list[dict[str, Any]] | list[Any]:
        return await self._call_comptox("get_chemicals_in_assay", str(aeid))

    async def discover_orphan_stressors_for_aops_with_diagnostics(
        self,
        aop_ids: list[str],
        *,
        limit: int = 25,
        per_aop_limit: int = 10,
        per_assay_chemical_limit: int = 25,
        min_hitcall: float = 0.9,
    ) -> dict[str, Any]:
        normalized_aop_ids = list(dict.fromkeys(aop_ids))
        if not normalized_aop_ids:
            raise ValueError("At least one aop_id is required")

        per_aop_candidate_limit = max(limit, min(per_aop_limit * per_assay_chemical_limit, 250))
        global_curated_index = {
            "dtxsids": set(),
            "casrns": set(),
            "names": set(),
        }
        if self.comptox and self.comptox.has_api_key:
            stressor_lists = await asyncio.gather(
                *(self._list_stressor_chemicals_for_aop(aop_id) for aop_id in normalized_aop_ids)
            )
            combined_stressors = [
                stressor
                for stressors in stressor_lists
                for stressor in stressors
            ]
            global_curated_index, _global_match_count, global_warnings = await self._build_curated_chemical_index(
                combined_stressors
            )
        else:
            global_warnings = []
        aggregated_candidates: dict[str, dict[str, Any]] = {}
        candidate_aliases: dict[str, str] = {}
        per_aop_diagnostics: list[dict[str, Any]] = []
        for aop_id in normalized_aop_ids:
            report = await self.discover_orphan_stressors_for_aop_with_diagnostics(
                aop_id,
                assay_limit=per_aop_limit,
                per_assay_chemical_limit=per_assay_chemical_limit,
                limit=per_aop_candidate_limit,
                min_hitcall=min_hitcall,
            )
            per_aop_diagnostics.append(report["diagnostics"])
            for candidate in report["results"]:
                normalized_chemical = {
                    "dtxsid": candidate.get("dtxsid"),
                    "casrn": candidate.get("casrn"),
                    "preferred_name": candidate.get("preferred_name"),
                }
                candidate_key = next(
                    (
                        candidate_aliases[alias]
                        for alias in _chemical_alias_keys(normalized_chemical)
                        if alias in candidate_aliases
                    ),
                    None,
                ) or _chemical_candidate_key(normalized_chemical)
                if candidate_key is None:
                    continue
                aggregated_candidate = aggregated_candidates.setdefault(
                    candidate_key,
                    {
                        "dtxsid": candidate.get("dtxsid"),
                        "casrn": candidate.get("casrn"),
                        "preferred_name": candidate.get("preferred_name"),
                        "aop_support_count": 0,
                        "supporting_aops": [],
                        "supporting_assay_count": 0,
                        "best_assay_rank": candidate.get("best_assay_rank"),
                        "max_specificity_score": candidate.get("max_specificity_score"),
                        "supporting_assays": [],
                        "_supporting_aops": set(),
                        "_seen_support": set(),
                    },
                )
                for alias in _chemical_alias_keys(normalized_chemical):
                    candidate_aliases.setdefault(alias, candidate_key)
                if aggregated_candidate["dtxsid"] is None:
                    aggregated_candidate["dtxsid"] = candidate.get("dtxsid")
                if aggregated_candidate["casrn"] is None:
                    aggregated_candidate["casrn"] = candidate.get("casrn")
                if aggregated_candidate["preferred_name"] is None:
                    aggregated_candidate["preferred_name"] = candidate.get("preferred_name")

                best_assay_rank = candidate.get("best_assay_rank")
                if best_assay_rank is not None:
                    current_best = aggregated_candidate.get("best_assay_rank")
                    if current_best is None or best_assay_rank < current_best:
                        aggregated_candidate["best_assay_rank"] = best_assay_rank

                max_specificity_score = candidate.get("max_specificity_score")
                if max_specificity_score is not None:
                    current_specificity = aggregated_candidate.get("max_specificity_score")
                    if current_specificity is None or max_specificity_score > current_specificity:
                        aggregated_candidate["max_specificity_score"] = max_specificity_score

                aggregated_candidate["_supporting_aops"].add(aop_id)
                for support in candidate.get("supporting_assays", []):
                    support_key = (aop_id, support.get("aeid"))
                    if support_key in aggregated_candidate["_seen_support"]:
                        continue
                    aggregated_candidate["_seen_support"].add(support_key)
                    aggregated_candidate["supporting_assays"].append(
                        {
                            "aop_id": aop_id,
                            "aeid": support.get("aeid"),
                            "assay_name": support.get("assay_name"),
                            "rank": support.get("rank"),
                            "specificity_score": support.get("specificity_score"),
                        }
                    )

        materialized_candidates: list[dict[str, Any]] = []
        for candidate in aggregated_candidates.values():
            normalized_chemical = {
                "dtxsid": candidate.get("dtxsid"),
                "casrn": candidate.get("casrn"),
                "preferred_name": candidate.get("preferred_name"),
            }
            if _chemical_matches_index(normalized_chemical, global_curated_index):
                continue
            supporting_aops = sorted(candidate.pop("_supporting_aops"))
            candidate.pop("_seen_support", None)
            candidate["supporting_assays"].sort(
                key=lambda item: (
                    item["rank"],
                    -(item["specificity_score"] if item["specificity_score"] is not None else -1.0),
                    item["aop_id"],
                    item["aeid"],
                )
            )
            candidate["supporting_aops"] = supporting_aops
            candidate["aop_support_count"] = len(supporting_aops)
            candidate["supporting_assay_count"] = len(candidate["supporting_assays"])
            materialized_candidates.append(candidate)

        materialized_candidates.sort(
            key=lambda item: (
                -item["aop_support_count"],
                -item["supporting_assay_count"],
                item["best_assay_rank"],
                -(item["max_specificity_score"] if item["max_specificity_score"] is not None else -1.0),
                item.get("preferred_name") or "",
            )
        )
        results = materialized_candidates[:limit]

        warnings: list[str] = []
        warnings.extend(global_warnings)
        if len(normalized_aop_ids) != len(aop_ids):
            warnings.append("Duplicate AOP identifiers were deduplicated before orphan-candidate aggregation.")
        if any(item.get("empty_reason") is not None for item in per_aop_diagnostics):
            warnings.append(
                "One or more AOPs returned no orphan candidates; inspect diagnostics.per_aop for details."
            )
        warnings = list(dict.fromkeys(warnings))

        return {
            "results": results,
            "diagnostics": {
                "requested_aop_ids": list(aop_ids),
                "processed_aop_ids": normalized_aop_ids,
                "returned_candidate_count": len(results),
                "per_aop": per_aop_diagnostics,
                "warnings": warnings,
            },
        }

    async def search_assays_for_key_event(
        self,
        key_event: dict[str, Any],
        *,
        limit: int = 25,
    ) -> dict[str, Any]:
        if not self.comptox:
            raise ValueError("CompTox client is required for key-event assay search")

        heuristic_terms = _derive_key_event_search_terms(
            key_event,
            expand_phenotype_phrases=False,
        )
        limitations = [
            "Assays are ranked using key-event-derived gene and phrase matches plus specificity-aware CompTox discovery ranking when available, with catalog and AOP-Wiki measurement-method fallbacks; this is not a curated KE-to-assay ontology mapping.",
        ]
        structured_gene_identifiers = _structured_gene_identifiers(key_event.get("gene_identifiers") or [])
        resolved_gene_symbols: list[str] = []
        if structured_gene_identifiers and self.hgnc:
            try:
                resolved_gene_symbols = await self._resolve_hgnc_gene_symbols(structured_gene_identifiers)
            except HgncError as exc:
                limitations.append(
                    "HGNC gene-symbol resolution was unavailable, so only title/alias-derived gene symbols were used."
                )
                limitations.append(f"HGNC detail: {exc}")
        elif structured_gene_identifiers:
            limitations.append(
                "Structured HGNC gene identifiers were available on the key event, but HGNC resolution was not configured."
            )
        elif key_event.get("gene_identifiers"):
            limitations.append(
                "Key-event gene identifiers were present but did not contain resolvable HGNC identifiers."
            )
        merged_gene_symbols = _merge_preserving_order(
            resolved_gene_symbols,
            heuristic_terms["gene_symbols"],
        )
        phrases = heuristic_terms["phrases"]
        if not merged_gene_symbols:
            phrases = _expand_phenotype_phrases(phrases)
        phrases = _finalize_phrases(phrases, merged_gene_symbols)
        derived_search_terms = {
            "structured_gene_identifiers": structured_gene_identifiers,
            "resolved_gene_symbols": resolved_gene_symbols,
            "gene_symbols": merged_gene_symbols[:8],
            "phrases": phrases[:8],
        }
        if structured_gene_identifiers and not resolved_gene_symbols and self.hgnc:
            limitations.append(
                "Structured HGNC gene identifiers were available, but none could be resolved to gene symbols."
            )

        if not derived_search_terms["gene_symbols"] and not derived_search_terms["phrases"]:
            limitations.append(
                "No structured or heuristic gene symbols or searchable phrases could be derived from the key event metadata."
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
            results = await self._call_comptox(
                "search_assay_catalog",
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
        query = self._templates.render_safe(
            "map_assay_to_aops", literals={"assay_id": assay_id}
        )
        try:
            payload = await self.client.query(query, cache_ttl_seconds=self.cache_ttl_seconds)
        except SparqlClientError as exc:
            payload = self._load_fixture("aop_db", "map_assay_to_aops", error=exc)
        bindings = payload.get("results", {}).get("bindings", [])
        results: list[dict[str, Any]] = []
        for row in bindings:
            aop = row.get("aop", {})
            results.append(
                {
                    "aop": {
                        "id": AOP_CURIE_RESOLVER.resolve(aop.get("value", "")),
                        "iri": aop.get("value"),
                        "title": row.get("title", {}).get("value"),
                    },
                    "assay_id": assay_id,
                }
            )
        return results

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

    async def _call_comptox(self, method_name: str, /, *args: Any, **kwargs: Any) -> Any:
        if not self.comptox:
            raise ValueError("CompTox client is required for this operation")
        method = getattr(self.comptox, method_name)
        return await asyncio.to_thread(method, *args, **kwargs)

    async def _gather_bounded(
        self,
        coroutines: list[Any],
        *,
        limit: int,
        return_exceptions: bool = False,
    ) -> list[Any]:
        semaphore = asyncio.Semaphore(max(1, limit))

        async def run(coroutine: Any) -> Any:
            async with semaphore:
                return await coroutine

        return await asyncio.gather(
            *(run(coroutine) for coroutine in coroutines),
            return_exceptions=return_exceptions,
        )

    async def _resolve_hgnc_gene_symbols(self, identifiers: list[str]) -> list[str]:
        if not self.hgnc:
            return []
        tasks = [
            asyncio.to_thread(self.hgnc.resolve_symbol, identifier)
            for identifier in identifiers
        ]
        resolved = await asyncio.gather(*tasks, return_exceptions=True)
        symbols: list[str] = []
        for item in resolved:
            if isinstance(item, Exception):
                if isinstance(item, HgncError):
                    raise item
                raise HgncError(str(item)) from item
            if item:
                symbols.append(item)
        return symbols

    async def _build_curated_chemical_index(
        self,
        stressors: list[dict[str, Any]],
    ) -> tuple[dict[str, set[str]], int, list[str]]:
        index = {
            "dtxsids": set(),
            "casrns": set(),
            "names": set(),
        }
        search_values: list[str] = []
        for stressor in stressors:
            casrn = stressor.get("casrn")
            if casrn:
                index["casrns"].add(str(casrn))
                if str(casrn) not in search_values:
                    search_values.append(str(casrn))
            label = stressor.get("label")
            normalized_label = _normalize_chemical_name(label)
            if normalized_label:
                index["names"].add(normalized_label)
                if str(label) not in search_values:
                    search_values.append(str(label))

        warnings: list[str] = []
        if not search_values:
            warnings.append(
                "Linked stressors lacked searchable CAS RN and label values, so curated-chemical exclusion relies only on exact identifiers already present in assay results."
            )
            return index, 0, warnings

        search_results = await self._gather_bounded(
            [
                self._call_comptox("search_equal", search_value)
                for search_value in search_values
            ],
            limit=self.comptox_concurrency_limit,
            return_exceptions=True,
        )
        resolved_dtxsids: set[str] = set()
        for search_value, search_result in zip(search_values, search_results, strict=False):
            if isinstance(search_result, Exception):
                warnings.append(
                    f"CompTox chemical resolution failed for curated stressor lookup '{search_value}': {search_result}"
                )
                continue
            if not search_result:
                continue
            matched_chemical = _normalize_assay_chemical_record(search_result[0])
            dtxsid = matched_chemical.get("dtxsid")
            if dtxsid:
                index["dtxsids"].add(dtxsid)
                resolved_dtxsids.add(dtxsid)
            casrn = matched_chemical.get("casrn")
            if casrn:
                index["casrns"].add(casrn)
            normalized_name = _normalize_chemical_name(matched_chemical.get("preferred_name"))
            if normalized_name:
                index["names"].add(normalized_name)
        return index, len(resolved_dtxsids), warnings

    async def _list_stressor_chemicals_for_aop(self, aop_id: str) -> list[dict[str, Any]]:
        query = self._templates.render_safe(
            "list_stressor_chemicals_for_aop", uris={"aop_iri": _aop_iri(aop_id)}
        )
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

    async def list_stressor_chemicals_for_aop(self, aop_id: str) -> list[dict[str, Any]]:
        try:
            return await self._list_stressor_chemicals_for_aop(aop_id)
        except SparqlClientError:
            return []


def _derive_key_event_search_terms(
    key_event: dict[str, Any],
    *,
    expand_phenotype_phrases: bool = True,
) -> dict[str, list[str]]:
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
    if not gene_symbols and expand_phenotype_phrases:
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


def _merge_preserving_order(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for value in group:
            if value and value not in merged:
                merged.append(value)
    return merged


def _structured_gene_identifiers(values: list[str]) -> list[str]:
    identifiers: list[str] = []
    for value in values:
        normalized = str(value).strip().upper()
        if not re.fullmatch(r"HGNC:\d+", normalized):
            continue
        if normalized not in identifiers:
            identifiers.append(normalized)
    return identifiers


def _assay_specificity_score(assay: dict[str, Any]) -> float | None:
    return compute_specificity_score(
        multi_active=assay.get("multi_conc_assay_chemical_count_active")
        or assay.get("multiConcActives"),
        multi_total=assay.get("multi_conc_assay_chemical_count_total"),
        single_active=assay.get("single_conc_assay_chemical_count_active")
        or assay.get("singleConcActive"),
        single_total=assay.get("single_conc_assay_chemical_count_total"),
    )


def _weighted_hitcall(max_hitcall: float, specificity_score: float | None) -> float:
    if specificity_score is None:
        return max_hitcall
    return max_hitcall * (0.5 + (0.5 * specificity_score))


def _normalize_assay_chemical_record(record: dict[str, Any] | str | Any) -> dict[str, str | None]:
    if isinstance(record, str):
        normalized = record.strip()
        if not normalized:
            return {"dtxsid": None, "casrn": None, "preferred_name": None}
        if re.fullmatch(r"DTXSID\d+", normalized, re.IGNORECASE):
            return {
                "dtxsid": normalized.upper(),
                "casrn": None,
                "preferred_name": None,
            }
        if re.fullmatch(r"\d{2,7}-\d{2}-\d", normalized):
            return {
                "dtxsid": None,
                "casrn": normalized,
                "preferred_name": None,
            }
        return {
            "dtxsid": None,
            "casrn": None,
            "preferred_name": normalized,
        }
    return {
        "dtxsid": _first_non_empty(
            record.get("dtxsid"),
            record.get("dsstoxSubstanceId"),
            record.get("dsstoxSubstanceID"),
        ),
        "casrn": _first_non_empty(
            record.get("casrn"),
            record.get("cas"),
            record.get("casNumber"),
        ),
        "preferred_name": _first_non_empty(
            record.get("preferredName"),
            record.get("preferred_name"),
            record.get("name"),
            record.get("chemicalName"),
        ),
    }


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _normalize_chemical_name(value: Any) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "", str(value).lower())
    return normalized or None


def _chemical_identity_available(record: dict[str, str | None]) -> bool:
    return bool(record.get("dtxsid") or record.get("casrn") or _normalize_chemical_name(record.get("preferred_name")))


def _chemical_candidate_key(record: dict[str, str | None]) -> str | None:
    return (
        record.get("dtxsid")
        or record.get("casrn")
        or _normalize_chemical_name(record.get("preferred_name"))
    )


def _chemical_alias_keys(record: dict[str, str | None]) -> list[str]:
    aliases: list[str] = []
    dtxsid = record.get("dtxsid")
    if dtxsid:
        aliases.append(f"dtxsid:{dtxsid}")
    casrn = record.get("casrn")
    if casrn:
        aliases.append(f"casrn:{casrn}")
    normalized_name = _normalize_chemical_name(record.get("preferred_name"))
    if normalized_name:
        aliases.append(f"name:{normalized_name}")
    return aliases


def _chemical_matches_index(
    record: dict[str, str | None],
    index: dict[str, set[str]],
) -> bool:
    dtxsid = record.get("dtxsid")
    if dtxsid and dtxsid in index["dtxsids"]:
        return True
    casrn = record.get("casrn")
    if casrn and casrn in index["casrns"]:
        return True
    normalized_name = _normalize_chemical_name(record.get("preferred_name"))
    if normalized_name and normalized_name in index["names"]:
        return True
    return False


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
