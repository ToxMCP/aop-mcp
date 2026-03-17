"""AOP-DB SPARQL adapter for chemical and assay mappings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .fixtures import FixtureNotFoundError, load_fixture
from .sparql_client import SparqlClient, SparqlClientError
from .sparql_client import TemplateCatalog as _TemplateCatalog
from .aop_wiki import _iri_to_curie  # reuse IRI normalization

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "aop_db"


from .comp_tox import CompToxClient


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
