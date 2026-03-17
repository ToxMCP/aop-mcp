"""Tool handlers wiring domain services to MCP."""

from __future__ import annotations

import asyncio
import csv
import io
import re
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, model_validator

from src.server.dependencies import (
    get_draft_store,
    get_aop_db_adapter,
    get_aop_wiki_adapter,
    get_semantic_tools,
    get_write_tools,
)
from src.tools.write import (
    DraftApplicability,
    KeyEventPayload,
    KeyEventRelationshipPayload,
    StressorLinkPayload,
)


class SearchAopsInput(BaseModel):
    text: Optional[str] = None
    limit: int = Field(default=25, ge=1, le=100)


async def search_aops(params: SearchAopsInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    results = await adapter.search_aops(text=params.text, limit=params.limit)
    return {"results": results}


class GetAopInput(BaseModel):
    aop_id: str


async def get_aop(params: GetAopInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    record = await adapter.get_aop(params.aop_id)
    return record


class GetKeyEventInput(BaseModel):
    key_event_id: str = Field(
        validation_alias=AliasChoices("key_event_id", "ke_id"),
    )


async def get_key_event(params: GetKeyEventInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    return await adapter.get_key_event(params.key_event_id)


class ListKeyEventsInput(BaseModel):
    aop_id: str


async def list_key_events(params: ListKeyEventsInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    items = await adapter.list_key_events(params.aop_id)
    return {"results": items}


class ListKersInput(BaseModel):
    aop_id: str


async def list_kers(params: ListKersInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    items = await adapter.list_kers(params.aop_id)
    return {"results": items}


class GetKerInput(BaseModel):
    ker_id: str


async def get_ker(params: GetKerInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    return await adapter.get_ker(params.ker_id)


class GetRelatedAopsInput(BaseModel):
    aop_id: str
    limit: int = Field(default=20, ge=1, le=100)


async def get_related_aops(params: GetRelatedAopsInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    source_aop = await adapter.get_aop(params.aop_id)
    related = await adapter.get_related_aops(params.aop_id, limit=params.limit)
    return {"aop": source_aop, "results": related}


class AssessAopConfidenceInput(BaseModel):
    aop_id: str


async def assess_aop_confidence(params: AssessAopConfidenceInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    aop = await adapter.get_aop_assessment(params.aop_id)
    key_events = await adapter.list_key_events(params.aop_id)
    kers = await adapter.list_kers(params.aop_id)

    key_event_ids = [item["id"] for item in key_events if item.get("id")]
    ker_ids = [item["id"] for item in kers if item.get("id")]
    key_event_details, ker_details = await asyncio.gather(
        asyncio.gather(*(adapter.get_key_event(item_id) for item_id in key_event_ids)),
        asyncio.gather(*(adapter.get_ker(item_id) for item_id in ker_ids)),
    )

    key_event_summaries = [_summarize_key_event(record) for record in key_event_details]
    ker_assessments = [_summarize_ker(record) for record in ker_details]
    coverage = _build_assessment_coverage(key_event_details, ker_details)
    applicability_summary = _build_applicability_summary(key_event_details)
    confidence_dimensions = _build_confidence_dimensions(
        ker_details,
    )
    supplemental_signals = _build_supplemental_signals(
        overall_evidence=aop.get("evidence_summary"),
    )
    heuristic_overall_call = _build_overall_confidence_call(
        coverage,
        confidence_dimensions,
    )
    limitations = _build_assessment_limitations(
        coverage,
        confidence_dimensions,
        applicability_summary,
        supplemental_signals,
    )
    oecd_alignment = _build_oecd_alignment_summary(confidence_dimensions)

    rationale = [
        f"AOP contains {coverage['key_event_count']} key events and {coverage['ker_count']} KERs.",
        f"{coverage['kers_with_biological_plausibility']}/{coverage['ker_count']} KERs include biological plausibility text.",
        f"{coverage['kers_with_empirical_support']}/{coverage['ker_count']} KERs include empirical support text.",
        f"{coverage['kers_with_quantitative_understanding']}/{coverage['ker_count']} KERs include quantitative understanding text.",
        f"{coverage['key_events_with_measurement_methods']}/{coverage['key_event_count']} key events include measurement guidance.",
    ]
    if supplemental_signals["aop_level_evidence_signal"]["heuristic_call"] != "not_reported":
        rationale.append(
            "Supplemental AOP-level evidence text suggests "
            f"{supplemental_signals['aop_level_evidence_signal']['heuristic_call'].replace('_', ' ')} support."
        )

    return {
        "aop": {
            **aop,
            "key_event_count": coverage["key_event_count"],
            "ker_count": coverage["ker_count"],
        },
        "coverage": coverage,
        "applicability_summary": applicability_summary,
        "confidence_dimensions": confidence_dimensions,
        "supplemental_signals": supplemental_signals,
        "oecd_alignment": oecd_alignment,
        "heuristic_overall_call": heuristic_overall_call,
        "rationale": rationale,
        "limitations": limitations,
        "key_events": key_event_summaries,
        "ker_assessments": ker_assessments,
    }


class FindPathsBetweenEventsInput(BaseModel):
    aop_id: str
    source_event_id: str
    target_event_id: str
    max_depth: int = Field(default=8, ge=1, le=20)
    limit: int = Field(default=10, ge=1, le=50)


async def find_paths_between_events(params: FindPathsBetweenEventsInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    key_events = await adapter.list_key_events(params.aop_id)
    kers = await adapter.list_kers(params.aop_id)

    key_event_titles = {item["id"]: item.get("title") for item in key_events if item.get("id")}
    source_event_id = _normalize_aop_element_id(params.source_event_id)
    target_event_id = _normalize_aop_element_id(params.target_event_id)

    adjacency: dict[str, list[dict[str, Any]]] = {}
    for ker in kers:
        upstream_id = ker.get("upstream", {}).get("id")
        downstream_id = ker.get("downstream", {}).get("id")
        if not upstream_id or not downstream_id:
            continue
        adjacency.setdefault(upstream_id, []).append(ker)

    paths: list[dict[str, Any]] = []

    def dfs(current_event_id: str, visited: set[str], ker_path: list[dict[str, Any]]) -> None:
        if len(paths) >= params.limit:
            return
        if len(ker_path) > params.max_depth:
            return
        if current_event_id == target_event_id:
            event_ids = [source_event_id]
            for edge in ker_path:
                downstream_id = edge["downstream"]["id"]
                event_ids.append(downstream_id)
            paths.append(
                {
                    "event_path": [
                        {
                            "id": event_id,
                            "title": key_event_titles.get(event_id),
                        }
                        for event_id in event_ids
                    ],
                    "ker_path": [
                        {
                            "id": edge.get("id"),
                            "upstream_event_id": edge["upstream"]["id"],
                            "downstream_event_id": edge["downstream"]["id"],
                        }
                        for edge in ker_path
                    ],
                }
            )
            return

        for edge in adjacency.get(current_event_id, []):
            downstream_id = edge["downstream"]["id"]
            if downstream_id in visited:
                continue
            dfs(downstream_id, visited | {downstream_id}, [*ker_path, edge])

    dfs(source_event_id, {source_event_id}, [])
    return {
        "aop_id": _normalize_aop_element_id(params.aop_id),
        "source_event_id": source_event_id,
        "target_event_id": target_event_id,
        "path_count": len(paths),
        "results": paths,
    }


class MapChemicalInput(BaseModel):
    inchikey: Optional[str] = None
    cas: Optional[str] = None
    name: Optional[str] = None

    @model_validator(mode="after")
    def ensure_identifier(self) -> "MapChemicalInput":
        if not (self.inchikey or self.cas or self.name):
            raise ValueError("Provide at least one identifier: inchikey, cas, or name")
        return self


async def map_chemical_to_aops(params: MapChemicalInput) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    records = await adapter.map_chemical_to_aops(
        inchikey=params.inchikey,
        cas=params.cas,
        name=params.name,
    )
    return {"results": records}


class MapAssayInput(BaseModel):
    assay_id: str


async def map_assay_to_aops(params: MapAssayInput) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    records = await adapter.map_assay_to_aops(params.assay_id)
    return {"results": records}


class SearchAssaysForKeyEventInput(BaseModel):
    key_event_id: str = Field(
        validation_alias=AliasChoices("key_event_id", "ke_id"),
    )
    limit: int = Field(default=25, ge=1, le=100)


async def search_assays_for_key_event(params: SearchAssaysForKeyEventInput) -> dict[str, Any]:
    wiki_adapter = get_aop_wiki_adapter()
    key_event = await wiki_adapter.get_key_event(params.key_event_id)

    db_adapter = get_aop_db_adapter()
    assay_search = await db_adapter.search_assays_for_key_event(
        key_event,
        limit=params.limit,
    )
    return {
        "key_event": key_event,
        **assay_search,
    }


class ListAssaysForAopInput(BaseModel):
    aop_id: str
    limit: int = Field(default=25, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def list_assays_for_aop(params: ListAssaysForAopInput) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    records = await adapter.list_assays_for_aop(
        params.aop_id,
        limit=params.limit,
        min_hitcall=params.min_hitcall,
    )
    return {"results": records}


class ListAssaysForAopsInput(BaseModel):
    aop_ids: list[str]
    limit: int = Field(default=25, ge=1, le=100)
    per_aop_limit: int = Field(default=15, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def ensure_aop_ids(self) -> "ListAssaysForAopsInput":
        if not self.aop_ids:
            raise ValueError("Provide at least one aop_id")
        return self


async def list_assays_for_aops(params: ListAssaysForAopsInput) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    records = await adapter.list_assays_for_aops(
        params.aop_ids,
        limit=params.limit,
        per_aop_limit=params.per_aop_limit,
        min_hitcall=params.min_hitcall,
    )
    return {"results": records}


class ListAssaysForQueryInput(BaseModel):
    query: str
    search_limit: int = Field(default=25, ge=1, le=100)
    aop_limit: int = Field(default=10, ge=1, le=100)
    limit: int = Field(default=25, ge=1, le=100)
    per_aop_limit: int = Field(default=15, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def list_assays_for_query(params: ListAssaysForQueryInput) -> dict[str, Any]:
    selected_aops, records = await _resolve_assays_from_query(
        params.query,
        search_limit=params.search_limit,
        aop_limit=params.aop_limit,
        limit=params.limit,
        per_aop_limit=params.per_aop_limit,
        min_hitcall=params.min_hitcall,
    )
    return {
        "query": params.query,
        "selected_aops": selected_aops,
        "results": records,
    }


class ExportAssaysTableInput(BaseModel):
    query: Optional[str] = None
    aop_ids: Optional[list[str]] = None
    format: Literal["csv", "tsv"] = "csv"
    search_limit: int = Field(default=25, ge=1, le=100)
    aop_limit: int = Field(default=10, ge=1, le=100)
    limit: int = Field(default=25, ge=1, le=100)
    per_aop_limit: int = Field(default=15, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def ensure_source(self) -> "ExportAssaysTableInput":
        if bool(self.query) == bool(self.aop_ids):
            raise ValueError("Provide exactly one of query or aop_ids")
        return self


async def export_assays_table(params: ExportAssaysTableInput) -> dict[str, Any]:
    selected_aops: list[dict[str, Any]]
    if params.query:
        selected_aops, records = await _resolve_assays_from_query(
            params.query,
            search_limit=params.search_limit,
            aop_limit=params.aop_limit,
            limit=params.limit,
            per_aop_limit=params.per_aop_limit,
            min_hitcall=params.min_hitcall,
        )
    else:
        adapter = get_aop_db_adapter()
        aop_ids = params.aop_ids or []
        selected_aops = [{"id": aop_id} for aop_id in aop_ids]
        records = await adapter.list_assays_for_aops(
            aop_ids,
            limit=params.limit,
            per_aop_limit=params.per_aop_limit,
            min_hitcall=params.min_hitcall,
        )

    return {
        "format": params.format,
        "filename": _build_export_filename(params.format, query=params.query, aop_ids=params.aop_ids or []),
        "row_count": len(records),
        "selected_aops": selected_aops,
        "content": _serialize_assay_rows(records, params.format),
    }


async def _resolve_assays_from_query(
    query: str,
    *,
    search_limit: int,
    aop_limit: int,
    limit: int,
    per_aop_limit: int,
    min_hitcall: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    wiki_adapter = get_aop_wiki_adapter()
    search_results = await wiki_adapter.search_aops(text=query, limit=search_limit)
    selected_aops = search_results[:aop_limit]
    selected_aop_ids = [row["id"] for row in selected_aops if row.get("id")]
    if not selected_aop_ids:
        return selected_aops, []

    db_adapter = get_aop_db_adapter()
    records = await db_adapter.list_assays_for_aops(
        selected_aop_ids,
        limit=limit,
        per_aop_limit=per_aop_limit,
        min_hitcall=min_hitcall,
    )
    return selected_aops, records


def _build_export_filename(format_name: str, *, query: str | None, aop_ids: list[str]) -> str:
    if query:
        return f"assays_{_slugify(query)}.{format_name}"
    return f"assays_{len(aop_ids)}_aops.{format_name}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "query"


def _serialize_assay_rows(rows: list[dict[str, Any]], format_name: str) -> str:
    fieldnames = [
        "aeid",
        "assay_name",
        "assay_component_endpoint_name",
        "assay_function_type",
        "target_family",
        "target_family_sub",
        "gene_symbols",
        "aop_support_count",
        "supporting_aops",
        "chemical_support_count",
        "supporting_chemicals",
        "supporting_dtxsids",
        "supporting_casrns",
        "stressor_labels",
        "max_hitcall",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        delimiter="," if format_name == "csv" else "\t",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        supporting_chemicals = row.get("supporting_chemicals", [])
        writer.writerow(
            {
                "aeid": row.get("aeid"),
                "assay_name": row.get("assay_name"),
                "assay_component_endpoint_name": row.get("assay_component_endpoint_name"),
                "assay_function_type": row.get("assay_function_type"),
                "target_family": row.get("target_family"),
                "target_family_sub": row.get("target_family_sub"),
                "gene_symbols": "|".join(row.get("gene_symbols", [])),
                "aop_support_count": row.get("aop_support_count", row.get("support_count")),
                "supporting_aops": "|".join(row.get("supporting_aops", [])),
                "chemical_support_count": row.get("chemical_support_count", len(supporting_chemicals)),
                "supporting_chemicals": "|".join(
                    chemical.get("preferred_name") or ""
                    for chemical in supporting_chemicals
                ),
                "supporting_dtxsids": "|".join(
                    chemical.get("dtxsid") or ""
                    for chemical in supporting_chemicals
                ),
                "supporting_casrns": "|".join(
                    chemical.get("casrn") or ""
                    for chemical in supporting_chemicals
                ),
                "stressor_labels": "|".join(
                    "|".join(chemical.get("stressor_labels", []))
                    for chemical in supporting_chemicals
                ),
                "max_hitcall": row.get("max_hitcall"),
            }
        )
    return output.getvalue()


class GetApplicabilityInput(BaseModel):
    species: Optional[str] = None
    life_stage: Optional[str] = None
    sex: Optional[str] = None


async def get_applicability(params: GetApplicabilityInput) -> dict[str, Any]:
    semantic = get_semantic_tools()
    return semantic.get_applicability(
        species=params.species,
        life_stage=params.life_stage,
        sex=params.sex,
    )


class EvidenceMatrixInput(BaseModel):
    entries: list[dict[str, Optional[str]]]


async def get_evidence_matrix(params: EvidenceMatrixInput) -> dict[str, Any]:
    semantic = get_semantic_tools()
    return semantic.get_evidence_matrix(params.entries)


class CreateDraftInputModel(BaseModel):
    draft_id: str
    title: str
    description: str
    adverse_outcome: str
    applicability: Optional[dict[str, Optional[str]]] = None
    references: Optional[list[dict[str, Any]]] = None
    author: str
    summary: str
    tags: Optional[list[str]] = None


async def create_draft_aop(params: CreateDraftInputModel) -> dict[str, Any]:
    write_tools = get_write_tools()
    applicability = None
    if params.applicability:
        applicability = DraftApplicability(
            species=params.applicability.get("species"),
            life_stage=params.applicability.get("life_stage"),
            sex=params.applicability.get("sex"),
        )
    result = write_tools.create_draft_aop(
        draft_id=params.draft_id,
        title=params.title,
        description=params.description,
        adverse_outcome=params.adverse_outcome,
        applicability=applicability,
        references=params.references,
        author=params.author,
        summary=params.summary,
        tags=params.tags,
    )
    return result


class KeyEventInputModel(BaseModel):
    draft_id: str
    version_id: str
    author: str
    summary: str
    identifier: str
    title: str
    event_type: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None


async def add_or_update_ke(params: KeyEventInputModel) -> dict[str, Any]:
    write_tools = get_write_tools()
    result = write_tools.add_or_update_ke(
        draft_id=params.draft_id,
        version_id=params.version_id,
        author=params.author,
        summary=params.summary,
        payload=KeyEventPayload(
            identifier=params.identifier,
            title=params.title,
            event_type=params.event_type,
            attributes=params.attributes,
        ),
    )
    return result


class KerInputModel(BaseModel):
    draft_id: str
    version_id: str
    author: str
    summary: str
    identifier: str
    upstream: str
    downstream: str
    plausibility: Optional[str] = None
    status: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None
    provenance: Optional[dict[str, Any]] = None


async def add_or_update_ker(params: KerInputModel) -> dict[str, Any]:
    write_tools = get_write_tools()
    result = write_tools.add_or_update_ker(
        draft_id=params.draft_id,
        version_id=params.version_id,
        author=params.author,
        summary=params.summary,
        payload=KeyEventRelationshipPayload(
            identifier=params.identifier,
            upstream=params.upstream,
            downstream=params.downstream,
            plausibility=params.plausibility,
            status=params.status,
            attributes=params.attributes,
            provenance=params.provenance,
        ),
    )
    return result


class StressorLinkInputModel(BaseModel):
    draft_id: str
    version_id: str
    author: str
    summary: str
    stressor_id: str
    label: str
    source: str
    target: str
    provenance: Optional[dict[str, Any]] = None


async def link_stressor(params: StressorLinkInputModel) -> dict[str, Any]:
    write_tools = get_write_tools()
    result = write_tools.link_stressor(
        draft_id=params.draft_id,
        version_id=params.version_id,
        author=params.author,
        summary=params.summary,
        payload=StressorLinkPayload(
            stressor_id=params.stressor_id,
            label=params.label,
            source=params.source,
            target=params.target,
            provenance=params.provenance,
        ),
    )
    return result


class ValidateDraftOecdInput(BaseModel):
    draft_id: str
    version_id: Optional[str] = None


async def validate_draft_oecd(params: ValidateDraftOecdInput) -> dict[str, Any]:
    draft_store = get_draft_store()
    draft = draft_store.get_draft(params.draft_id)
    if draft is None:
        raise KeyError(f"Draft '{params.draft_id}' not found")

    version = draft.versions[-1]
    if params.version_id:
        for candidate in draft.versions:
            if candidate.version_id == params.version_id:
                version = candidate
                break
        else:
            raise KeyError(f"Version '{params.version_id}' not found in draft '{params.draft_id}'")

    entities = list(version.graph.entities.values())
    relationships = list(version.graph.relationships.values())
    aop_entity = next((entity for entity in entities if entity.type == "AdverseOutcomePathway"), None)
    key_events = [entity for entity in entities if entity.type == "KeyEvent"]
    kers = [rel for rel in relationships if rel.type == "KeyEventRelationship"]
    stressor_links = [rel for rel in relationships if rel.type == "StressorLink"]

    checks: list[dict[str, Any]] = []

    def add_check(check_id: str, label: str, passed: bool, severity: str, message: str) -> None:
        checks.append(
            {
                "id": check_id,
                "label": label,
                "status": "pass" if passed else "fail",
                "severity": severity,
                "message": message,
            }
        )

    add_check(
        "aop_root",
        "Draft contains a root AOP entity",
        aop_entity is not None,
        "error",
        "Create a draft AOP root entity before running OECD-style checks.",
    )

    if aop_entity is not None:
        title = str(aop_entity.attributes.get("title") or "").strip()
        add_check(
            "title_present",
            "AOP root includes a title",
            bool(title),
            "error",
            "Add a descriptive AOP title.",
        )
        add_check(
            "title_format",
            "Title follows OECD 'MIE leading to AO' guidance",
            bool(re.search(r"leading to", title, flags=re.IGNORECASE)),
            "warning",
            "Use the form 'MIE leading to AO' or 'MIE leading to AO via distinctive KE' where possible.",
        )
        add_check(
            "description_present",
            "AOP root includes a summary or abstract",
            bool(str(aop_entity.attributes.get("description") or "").strip()),
            "warning",
            "Add a concise abstract/summary describing the pathway and major knowledge gaps.",
        )
        add_check(
            "adverse_outcome_present",
            "AOP root records an adverse outcome",
            bool(str(aop_entity.attributes.get("adverse_outcome") or "").strip()),
            "warning",
            "Set the adverse outcome on the root AOP entity.",
        )
        add_check(
            "applicability_present",
            "AOP root captures applicability metadata",
            bool(aop_entity.attributes.get("applicability")),
            "warning",
            "Add species / life stage / sex applicability metadata on the draft root.",
        )
        references = aop_entity.attributes.get("references") or []
        add_check(
            "references_present",
            "AOP root has references",
            bool(references),
            "warning",
            "Add at least one reference supporting the AOP summary.",
        )
        add_check(
            "graphical_representation_present",
            "AOP root includes a graphical representation reference",
            any(
                key in aop_entity.attributes
                for key in ("graphical_representation", "diagram", "graph", "image_url")
            ),
            "warning",
            "Store a diagram or reference to a graphical AOP representation on the root entity.",
        )
        add_check(
            "contact_present",
            "AOP root includes author/contact metadata",
            any(
                key in aop_entity.attributes
                for key in ("corresponding_author", "point_of_contact", "authors", "contributors")
            ),
            "warning",
            "Add corresponding author / point-of-contact metadata for review workflows.",
        )

    add_check(
        "key_event_count",
        "Draft contains at least two key events",
        len(key_events) >= 2,
        "error",
        "Add the key events that define the pathway before review.",
    )
    add_check(
        "ker_count",
        "Draft contains at least one key event relationship",
        len(kers) >= 1,
        "error",
        "Add the KERs connecting the draft key events.",
    )
    add_check(
        "stressor_links",
        "Draft contains at least one linked stressor",
        len(stressor_links) >= 1,
        "warning",
        "Link one or more stressors where known; this is especially useful for MIE-centric review.",
    )

    measurement_keys = {"measurement", "measurement_methods", "how_it_is_measured", "methods"}
    applicability_keys = {
        "applicability",
        "species",
        "sex",
        "life_stage",
        "taxonomic_applicability",
        "taxa",
    }
    ke_with_measurement = sum(
        1
        for entity in key_events
        if any(entity.attributes.get(key) for key in measurement_keys)
    )
    ke_with_applicability = sum(
        1
        for entity in key_events
        if any(entity.attributes.get(key) for key in applicability_keys)
    )
    add_check(
        "ke_measurement_coverage",
        "Key events include measurement/detection guidance",
        ke_with_measurement == len(key_events) and len(key_events) > 0,
        "warning",
        f"{ke_with_measurement}/{len(key_events)} key events include measurement guidance.",
    )
    add_check(
        "ke_applicability_coverage",
        "Key events include applicability metadata",
        ke_with_applicability == len(key_events) and len(key_events) > 0,
        "warning",
        f"{ke_with_applicability}/{len(key_events)} key events include applicability metadata.",
    )

    ker_with_plausibility = sum(
        1
        for rel in kers
        if rel.attributes.get("plausibility") or rel.attributes.get("biological_plausibility")
    )
    ker_with_empirical_support = sum(
        1
        for rel in kers
        if rel.attributes.get("empirical_support")
        or rel.attributes.get("evidence")
        or rel.attributes.get("evidence_supporting_this_ker")
    )
    ker_with_quantitative_support = sum(
        1
        for rel in kers
        if rel.attributes.get("quantitative_understanding")
        or rel.attributes.get("response_response_relationship")
    )
    add_check(
        "ker_plausibility_coverage",
        "KERs include biological plausibility text",
        ker_with_plausibility == len(kers) and len(kers) > 0,
        "warning",
        f"{ker_with_plausibility}/{len(kers)} KERs include biological plausibility support.",
    )
    add_check(
        "ker_empirical_support_coverage",
        "KERs include empirical support",
        ker_with_empirical_support == len(kers) and len(kers) > 0,
        "warning",
        f"{ker_with_empirical_support}/{len(kers)} KERs include empirical support content.",
    )
    add_check(
        "ker_quantitative_support_coverage",
        "KERs include quantitative understanding",
        ker_with_quantitative_support == len(kers) and len(kers) > 0,
        "warning",
        f"{ker_with_quantitative_support}/{len(kers)} KERs include quantitative understanding content.",
    )

    error_count = sum(1 for check in checks if check["status"] == "fail" and check["severity"] == "error")
    warning_count = sum(1 for check in checks if check["status"] == "fail" and check["severity"] == "warning")
    score = max(0, 100 - error_count * 20 - warning_count * 5)

    return {
        "draft_id": draft.draft_id,
        "version_id": version.version_id,
        "summary": {
            "error_count": error_count,
            "warning_count": warning_count,
            "ready_for_review": error_count == 0,
            "score": score,
        },
        "results": checks,
    }


def _summarize_key_event(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "title": record.get("title"),
        "measurement_method_count": len(record.get("measurement_methods", [])),
        "taxonomic_applicability": record.get("taxonomic_applicability", []),
        "sex_applicability": record.get("sex_applicability"),
        "life_stage_applicability": record.get("life_stage_applicability"),
        "level_of_biological_organization": record.get("level_of_biological_organization"),
        "organ_context": record.get("organ_context", []),
        "cell_type_context": record.get("cell_type_context", []),
    }


def _summarize_ker(record: dict[str, Any]) -> dict[str, Any]:
    biological_plausibility = record.get("biological_plausibility")
    empirical_support = record.get("empirical_support")
    quantitative_understanding = record.get("quantitative_understanding")
    return {
        "id": record.get("id"),
        "title": record.get("title"),
        "upstream": record.get("upstream"),
        "downstream": record.get("downstream"),
        "biological_plausibility": biological_plausibility,
        "empirical_support": empirical_support,
        "quantitative_understanding": quantitative_understanding,
        "biological_plausibility_call": _extract_support_call(biological_plausibility),
        "empirical_support_call": _extract_support_call(empirical_support),
        "quantitative_understanding_call": _extract_support_call(quantitative_understanding),
    }


def _build_assessment_coverage(
    key_event_details: list[dict[str, Any]],
    ker_details: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "key_event_count": len(key_event_details),
        "ker_count": len(ker_details),
        "key_events_with_measurement_methods": sum(
            1 for record in key_event_details if record.get("measurement_methods")
        ),
        "key_events_with_taxonomic_applicability": sum(
            1 for record in key_event_details if record.get("taxonomic_applicability")
        ),
        "key_events_with_sex_applicability": sum(
            1 for record in key_event_details if record.get("sex_applicability")
        ),
        "key_events_with_life_stage_applicability": sum(
            1 for record in key_event_details if record.get("life_stage_applicability")
        ),
        "kers_with_biological_plausibility": sum(
            1 for record in ker_details if record.get("biological_plausibility")
        ),
        "kers_with_empirical_support": sum(
            1 for record in ker_details if record.get("empirical_support")
        ),
        "kers_with_quantitative_understanding": sum(
            1 for record in ker_details if record.get("quantitative_understanding")
        ),
    }


def _build_applicability_summary(key_event_details: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "basis": "Aggregated from key event metadata because AOP-level applicability is not consistently exposed in the current RDF export.",
        "taxonomic_applicability": _collect_unique(
            record.get("taxonomic_applicability", []) for record in key_event_details
        ),
        "sex_applicability": _collect_unique_scalar(
            record.get("sex_applicability") for record in key_event_details
        ),
        "life_stage_applicability": _collect_unique_scalar(
            record.get("life_stage_applicability") for record in key_event_details
        ),
        "level_of_biological_organization": _collect_unique_scalar(
            record.get("level_of_biological_organization") for record in key_event_details
        ),
        "organ_context": _collect_unique(record.get("organ_context", []) for record in key_event_details),
        "cell_type_context": _collect_unique(
            record.get("cell_type_context", []) for record in key_event_details
        ),
    }


def _build_confidence_dimensions(
    ker_details: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(ker_details)
    plausibility_calls = [
        _extract_support_call(record.get("biological_plausibility"))
        for record in ker_details
        if record.get("biological_plausibility")
    ]
    empirical_calls = [
        _extract_support_call(record.get("empirical_support"))
        for record in ker_details
        if record.get("empirical_support")
    ]
    quantitative_calls = [
        _extract_support_call(record.get("quantitative_understanding"))
        for record in ker_details
        if record.get("quantitative_understanding")
    ]

    return {
        "biological_plausibility": {
            "heuristic_call": _aggregate_dimension_call(plausibility_calls, total),
            "coverage": {"present": len(plausibility_calls), "total": total},
            "basis": "Aggregated from KER biological plausibility text.",
            "oecd_dimension": True,
        },
        "empirical_support": {
            "heuristic_call": _aggregate_dimension_call(empirical_calls, total),
            "coverage": {"present": len(empirical_calls), "total": total},
            "basis": "Aggregated from KER empirical support text.",
            "oecd_dimension": True,
        },
        "quantitative_understanding": {
            "heuristic_call": _aggregate_dimension_call(quantitative_calls, total),
            "coverage": {"present": len(quantitative_calls), "total": total},
            "basis": "Aggregated from KER quantitative understanding text.",
            "oecd_dimension": True,
        },
        "essentiality_of_key_events": {
            "heuristic_call": "not_assessed",
            "coverage": {"present": 0, "total": total},
            "basis": "Key-event essentiality is not directly surfaced in the current RDF export, so this tool does not assign an essentiality score.",
            "oecd_dimension": True,
        },
    }


def _build_supplemental_signals(*, overall_evidence: str | None) -> dict[str, Any]:
    overall_evidence_call = _extract_support_call(overall_evidence)
    return {
        "aop_level_evidence_signal": {
            "heuristic_call": overall_evidence_call,
            "coverage": {"present": 1 if overall_evidence else 0, "total": 1},
            "basis": "Derived from AOP-level free-text evidence when present. This is supplemental context and not an OECD core confidence dimension.",
            "oecd_dimension": False,
        }
    }


def _build_overall_confidence_call(
    coverage: dict[str, int],
    confidence_dimensions: dict[str, Any],
) -> str:
    ker_count = coverage["ker_count"]
    if ker_count == 0:
        return "sparse_evidence"

    if (
        coverage["kers_with_biological_plausibility"] == 0
        and coverage["kers_with_empirical_support"] == 0
        and coverage["kers_with_quantitative_understanding"] == 0
    ):
        return "sparse_evidence"

    plausibility_call = confidence_dimensions["biological_plausibility"]["heuristic_call"]
    empirical_call = confidence_dimensions["empirical_support"]["heuristic_call"]
    quantitative_call = confidence_dimensions["quantitative_understanding"]["heuristic_call"]

    if (
        plausibility_call in {"strong", "moderate"}
        and empirical_call in {"strong", "moderate"}
        and quantitative_call in {"strong", "moderate"}
        and confidence_dimensions["essentiality_of_key_events"]["heuristic_call"] in {"strong", "moderate"}
    ):
        return "high"

    if plausibility_call in {"strong", "moderate"} and empirical_call in {"strong", "moderate"}:
        return "moderate"

    return "low"


def _build_assessment_limitations(
    coverage: dict[str, int],
    confidence_dimensions: dict[str, Any],
    applicability_summary: dict[str, Any],
    supplemental_signals: dict[str, Any],
) -> list[str]:
    limitations = [
        "Key-event essentiality is not directly surfaced in the current RDF export, so this assessment does not assign an OECD essentiality score.",
    ]
    if supplemental_signals["aop_level_evidence_signal"]["heuristic_call"] == "not_reported":
        limitations.append(
            "No supplemental AOP-level evidence text was available, so the assessment relies on the OECD core dimensions that are exposed in KE/KER metadata."
        )
    else:
        limitations.append(
            "AOP-level evidence text is reported separately as a supplemental signal and is not used as an OECD core confidence dimension."
        )
    if coverage["kers_with_quantitative_understanding"] < coverage["ker_count"]:
        limitations.append(
            "Quantitative understanding text is missing for one or more KERs."
        )
    if not applicability_summary["taxonomic_applicability"] and not applicability_summary["sex_applicability"]:
        limitations.append(
            "Applicability summary is sparse and is aggregated from key-event metadata rather than a dedicated AOP-level applicability field."
        )
    return limitations


def _build_oecd_alignment_summary(confidence_dimensions: dict[str, Any]) -> dict[str, Any]:
    missing_dimensions = [
        dimension_name
        for dimension_name, dimension in confidence_dimensions.items()
        if dimension.get("heuristic_call") == "not_assessed"
    ]
    return {
        "status": "partial" if missing_dimensions else "core_dimensions_available",
        "core_dimensions": list(confidence_dimensions.keys()),
        "missing_dimensions": missing_dimensions,
        "notes": [
            "Overall OECD confidence is defined by biological plausibility, empirical support, quantitative understanding, and KE essentiality.",
            "This tool currently approximates the first three dimensions from KER text and reports KE essentiality as unavailable when the RDF export does not expose it.",
        ],
    }


def _collect_unique(values: list[list[str]] | Any) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for group in values:
        for value in group:
            if value and value not in seen:
                seen.add(value)
                items.append(value)
    return items


def _collect_unique_scalar(values: Any) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            items.append(value)
    return items


def _aggregate_dimension_call(calls: list[str], total: int) -> str:
    if total == 0 or not calls:
        return "not_reported"
    coverage_ratio = len(calls) / total
    average_score = sum(_SUPPORT_CALL_SCORES.get(call, 1.5) for call in calls) / len(calls)
    if coverage_ratio >= 0.8 and average_score >= 2.6:
        return "strong"
    if coverage_ratio >= 0.5 and average_score >= 1.8:
        return "moderate"
    return "low"


_SUPPORT_CALL_SCORES = {
    "low": 1.0,
    "mixed": 1.5,
    "reported": 1.5,
    "moderate": 2.0,
    "moderate_to_strong": 2.5,
    "strong": 3.0,
}


def _extract_support_call(text: str | None) -> str:
    if not text:
        return "not_reported"
    normalized = text.lower()
    if re.search(r"\b(moderate)\s*(to|-|/)\s*(strong)\b", normalized):
        return "moderate_to_strong"
    if re.search(r"\b(strong)\s*(to|-|/)\s*(moderate)\b", normalized):
        return "moderate_to_strong"
    if re.search(r"\b(is|are|was|were)\s+strong\b", normalized):
        return "strong"
    if re.search(r"\b(is|are|was|were)\s+moderate\b", normalized):
        return "moderate"
    if re.search(r"\b(is|are|was|were)\s+(low|weak)\b", normalized):
        return "low"
    if "strong mechanistic rationale" in normalized or "strong biological rationale" in normalized:
        return "strong"
    if "moderate mechanistic rationale" in normalized or "moderate biological rationale" in normalized:
        return "moderate"
    support_dimension_match = re.search(
        r"\b(strong|moderate|low|weak)\s+"
        r"(biological plausibility|empirical support|quantitative support|quantitative understanding|mechanistic rationale|rationale)\b",
        normalized,
    )
    if support_dimension_match:
        level = support_dimension_match.group(1)
        if level == "strong":
            return "strong"
        if level == "moderate":
            return "moderate"
        return "low"
    if re.search(r"\b(strong|high)\s+(support|evidence|confidence)\b", normalized):
        return "strong"
    if re.search(r"\bmoderate\s+(support|evidence|confidence)\b", normalized):
        return "moderate"
    if re.search(r"\b(low|weak)\s+(support|evidence|confidence)\b", normalized):
        return "low"
    citation_count = normalized.count("et al.")
    if citation_count >= 3 and ("correlated" in normalized or "concordance" in normalized):
        return "strong"
    if citation_count >= 2 and (
        "correlated" in normalized
        or "dose" in normalized
        or "temporal" in normalized
        or "concordance" in normalized
        or "yes yes" in normalized
    ):
        return "moderate"
    if "plausible but in need of further study" in normalized:
        return "mixed"
    if "causal relationship" in normalized or "consistent response" in normalized:
        return "strong"
    if "statistically significant" in normalized or "dose-dependent" in normalized:
        return "moderate"
    if "plausible" in normalized:
        return "moderate"
    if re.search(r"\buncertaint|inconsisten|conflict", normalized):
        return "mixed"
    return "reported"


def _normalize_aop_element_id(value: str) -> str:
    if value.startswith("https://identifiers.org/aop.events/"):
        return f"KE:{value.rsplit('/', 1)[-1]}"
    if value.startswith("http://aopwiki.org/events/"):
        return f"KE:{value.rsplit('/', 1)[-1]}"
    if value.startswith("https://identifiers.org/aop.relationships/"):
        return f"KER:{value.rsplit('/', 1)[-1]}"
    if value.startswith("http://aopwiki.org/relationships/"):
        return f"KER:{value.rsplit('/', 1)[-1]}"
    if value.startswith("https://identifiers.org/aop/"):
        return f"AOP:{value.rsplit('/', 1)[-1]}"
    if value.startswith("http://aopwiki.org/aops/"):
        return f"AOP:{value.rsplit('/', 1)[-1]}"
    return value
