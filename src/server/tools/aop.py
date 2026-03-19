"""Tool handlers wiring domain services to MCP."""

from __future__ import annotations

import asyncio
import csv
import io
import re
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

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
    is_governed_ke_essentiality,
    normalize_key_event_attributes,
)
from src.tools import validate_payload


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
    wiki_adapter = get_aop_wiki_adapter()
    db_adapter = get_aop_db_adapter()
    core_record, assessment_record, stressor_records = await asyncio.gather(
        wiki_adapter.get_aop(params.aop_id),
        wiki_adapter.get_aop_assessment(params.aop_id),
        db_adapter.list_stressor_chemicals_for_aop(params.aop_id),
    )
    record = _normalize_aop_record(
        core_record,
        assessment_record=assessment_record,
        stressor_records=stressor_records,
    )
    validate_payload(record, namespace="read", name="get_aop.response.schema")
    return record


class GetKeyEventInput(BaseModel):
    key_event_id: str = Field(
        validation_alias=AliasChoices("key_event_id", "ke_id"),
    )


async def get_key_event(params: GetKeyEventInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    record = _normalize_key_event_record(await adapter.get_key_event(params.key_event_id))
    validate_payload(record, namespace="read", name="get_key_event.response.schema")
    return record


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
    raw_record = await adapter.get_ker(params.ker_id)
    upstream_id = raw_record.get("upstream", {}).get("id")
    downstream_id = raw_record.get("downstream", {}).get("id")
    upstream_record, downstream_record = await asyncio.gather(
        _get_key_event_if_available(adapter, upstream_id),
        _get_key_event_if_available(adapter, downstream_id),
    )
    record = _normalize_ker_record(
        raw_record,
        upstream_record=upstream_record,
        downstream_record=downstream_record,
    )
    validate_payload(record, namespace="read", name="get_ker.response.schema")
    return record


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
        aop,
        key_event_details,
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
    normalized_aop = _normalize_aop_record(aop, assessment_record=aop)

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

    result = {
        "aop": {
            **normalized_aop,
            "key_event_count": coverage["key_event_count"],
            "ker_count": coverage["ker_count"],
        },
        "coverage": coverage,
        "overall_applicability": _normalize_applicability_summary(
            applicability_summary,
            key_event_details=key_event_details,
        ),
        "applicability_summary": applicability_summary,
        "biological_plausibility": confidence_dimensions["biological_plausibility"],
        "empirical_support": confidence_dimensions["empirical_support"],
        "quantitative_understanding": confidence_dimensions["quantitative_understanding"],
        "essentiality_of_key_events": confidence_dimensions["essentiality_of_key_events"],
        "confidence_dimensions": confidence_dimensions,
        "supplemental_signals": supplemental_signals,
        "oecd_alignment": oecd_alignment,
        "overall_call": heuristic_overall_call,
        "heuristic_overall_call": heuristic_overall_call,
        "rationale": rationale,
        "limitations": limitations,
        "key_events": key_event_summaries,
        "ker_assessments": ker_assessments,
        "provenance": [
            _make_provenance(
                source="aop_wiki_rdf",
                field="assessment_aggregation",
                transformation="phase1_oecd_alignment_normalization",
                confidence="moderate",
            )
        ],
    }
    validate_payload(result, namespace="read", name="assess_aop_confidence.response.schema")
    return result


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
    class KeyEventEssentialityInputModel(BaseModel):
        evidence_call: Literal["high", "moderate", "low", "not_reported", "not_assessed"]
        rationale: str
        references: list[dict[str, Any]] = Field(default_factory=list)
        provenance: list[dict[str, Any]] = Field(default_factory=list)

    class KeyEventAttributesInputModel(BaseModel):
        model_config = ConfigDict(extra="allow")
        essentiality: Optional["KeyEventInputModel.KeyEventEssentialityInputModel"] = None

    draft_id: str
    version_id: str
    author: str
    summary: str
    identifier: str
    title: str
    event_type: Optional[str] = None
    attributes: Optional["KeyEventInputModel.KeyEventAttributesInputModel"] = None

    @model_validator(mode="after")
    def _validate_governed_essentiality(self) -> "KeyEventInputModel":
        raw_attributes = None
        if self.attributes is not None:
            raw_attributes = self.attributes.model_dump(exclude_none=True)
        normalize_key_event_attributes(raw_attributes)
        return self


async def add_or_update_ke(params: KeyEventInputModel) -> dict[str, Any]:
    write_tools = get_write_tools()
    attributes = None
    if params.attributes is not None:
        attributes = normalize_key_event_attributes(params.attributes.model_dump(exclude_none=True))
    result = write_tools.add_or_update_ke(
        draft_id=params.draft_id,
        version_id=params.version_id,
        author=params.author,
        summary=params.summary,
        payload=KeyEventPayload(
            identifier=params.identifier,
            title=params.title,
            event_type=params.event_type,
            attributes=attributes,
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
    ke_with_governed_essentiality = sum(
        1
        for entity in key_events
        if is_governed_ke_essentiality(entity.attributes.get("essentiality"))
    )
    ke_with_invalid_essentiality = sum(
        1
        for entity in key_events
        if entity.attributes.get("essentiality") is not None
        and not is_governed_ke_essentiality(entity.attributes.get("essentiality"))
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
    add_check(
        "ke_essentiality_shape",
        "Governed KE essentiality records follow the draft contract",
        ke_with_invalid_essentiality == 0,
        "error",
        (
            "Key-event essentiality metadata must use the governed object form "
            "{evidence_call, rationale, references?, provenance?}."
        ),
    )
    add_check(
        "ke_essentiality_coverage",
        "Key events include explicit essentiality status",
        ke_with_governed_essentiality == len(key_events) and len(key_events) > 0,
        "warning",
        (
            f"{ke_with_governed_essentiality}/{len(key_events)} key events include governed essentiality "
            "metadata; explicit 'not_assessed' or 'not_reported' counts as coverage."
        ),
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


def _make_provenance(
    *,
    source: str,
    field: str,
    transformation: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "field": field,
        "transformation": transformation,
        "confidence": confidence,
    }


def _default_iri_for_identifier(identifier: str | None) -> str | None:
    if not identifier or ":" not in identifier:
        return None
    prefix, value = identifier.split(":", 1)
    if not value:
        return None
    if prefix == "AOP":
        return f"https://identifiers.org/aop/{value}"
    if prefix == "KE":
        return f"https://identifiers.org/aop.events/{value}"
    if prefix == "KER":
        return f"https://identifiers.org/aop.relationships/{value}"
    return None


def _normalize_link_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "iri": record.get("iri") or _default_iri_for_identifier(record.get("id")),
        "title": record.get("title"),
    }


def _is_identifier_like(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith(("http://", "https://")) or bool(re.match(r"^[A-Za-z][A-Za-z0-9_.-]*:[^\s]+$", value))


def _build_ontology_term(
    value: str | None,
    *,
    source_field: str,
    source: str = "aop_wiki_rdf",
    label: str | None = None,
    transformation: str | None = None,
    confidence: str | None = "moderate",
) -> dict[str, Any] | None:
    if not value:
        return None
    return {
        "id": value if _is_identifier_like(value) else None,
        "label": label if label is not None else (None if _is_identifier_like(value) else value),
        "source_field": source_field,
        "provenance": [
            _make_provenance(
                source=source,
                field=source_field,
                transformation=transformation,
                confidence=confidence,
            )
        ],
    }


def _build_applicability_term(
    value: str | None,
    *,
    source_field: str,
    source: str = "aop_wiki_rdf",
    label: str | None = None,
    evidence_call: str = "not_reported",
    rationale: str | None = None,
) -> dict[str, Any] | None:
    term = _build_ontology_term(
        value,
        source_field=source_field,
        source=source,
        label=label,
        transformation="normalized_for_oecd_phase1",
    )
    if term is None:
        return None
    provenance = list(term["provenance"])
    provenance.append(
        _make_provenance(
            source=source,
            field=source_field,
            transformation="applicability_term_wrapper",
            confidence="moderate",
        )
    )
    return {
        "term": term,
        "evidence_call": evidence_call,
        "rationale": rationale,
        "references": [],
        "provenance": provenance,
    }


def _get_reference_count(references: list[dict[str, Any]] | None) -> int:
    return len(references or [])


def _build_direct_applicability_term(
    value: str | None,
    *,
    source_field: str,
    references: list[dict[str, Any]] | None,
    source: str = "aop_wiki_rdf",
    label: str | None = None,
) -> dict[str, Any] | None:
    reference_count = _get_reference_count(references)
    evidence_call = "moderate" if reference_count else "low"
    rationale = (
        "Structured applicability term asserted in AOP-Wiki KE metadata and the KE exposes supporting references. "
        "The current RDF export does not expose applicability-specific evidence strength separately."
        if reference_count
        else "Structured applicability term asserted in AOP-Wiki KE metadata, but the current RDF export does not expose applicability-specific evidence strength or supporting references."
    )
    term = _build_applicability_term(
        value,
        source_field=source_field,
        source=source,
        label=label,
        evidence_call=evidence_call,
        rationale=rationale,
    )
    if term is None:
        return None
    term["references"] = list(references or [])
    term["provenance"].append(
        _make_provenance(
            source=source,
            field=source_field,
            transformation="phase3_direct_applicability_support_heuristic",
            confidence="moderate" if reference_count else "low",
        )
    )
    return term


def _build_measurement_method_detail(
    label: str | None,
    *,
    source_field: str = "measurement_methods",
    source: str = "aop_wiki_rdf",
) -> dict[str, Any] | None:
    if not label:
        return None
    return {
        "label": label,
        "method_type": None,
        "directness": "unknown",
        "fit_for_purpose": "not_reported",
        "repeatability": "not_reported",
        "reproducibility": "not_reported",
        "regulatory_acceptance": "unknown",
        "references": [],
        "provenance": [
            _make_provenance(
                source=source,
                field=source_field,
                transformation="measurement_label_only_phase1",
                confidence="low",
            )
        ],
    }


def _normalize_reference_records(references: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for item in references or []:
        record = {
            "label": item.get("label"),
            "identifier": item.get("identifier"),
            "source": item.get("source"),
        }
        dedupe_key = (record["identifier"], record["label"], record["source"])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(record)
    return normalized


def _extract_record_values(record: dict[str, Any] | None, field: str) -> list[str]:
    if not record:
        return []
    value = record.get(field)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def _build_summary_applicability_terms(
    key_event_details: list[dict[str, Any]],
    *,
    field: str,
    source_field: str,
) -> list[dict[str, Any]]:
    total = len(key_event_details)
    if total == 0:
        return []

    ordered_values: list[str] = []
    seen_values: set[str] = set()
    for record in key_event_details:
        for value in _extract_record_values(record, field):
            if value not in seen_values:
                seen_values.add(value)
                ordered_values.append(value)

    results: list[dict[str, Any]] = []
    for value in ordered_values:
        supporting_records = [
            record for record in key_event_details if value in _extract_record_values(record, field)
        ]
        supporting_reference_records = _normalize_reference_records(
            [
                reference
                for record in supporting_records
                for reference in record.get("references", [])
            ]
        )
        support_count = len(supporting_records)
        referenced_support_count = sum(
            1 for record in supporting_records if _get_reference_count(record.get("references")) > 0
        )
        support_ratio = support_count / total
        if support_count == total and referenced_support_count >= max(1, min(total, 2)):
            evidence_call = "high"
        elif support_ratio >= 0.5 or referenced_support_count > 0:
            evidence_call = "moderate"
        else:
            evidence_call = "low"
        rationale = (
            f"Derived from {support_count}/{total} key events; {referenced_support_count} supporting key events expose references. "
            "This is a consistency-based heuristic because the current RDF export does not expose a dedicated applicability strength field."
        )
        term = _build_applicability_term(
            value,
            source_field=source_field,
            source="derived_from_ke_metadata",
            evidence_call=evidence_call,
            rationale=rationale,
        )
        if term is None:
            continue
        term["references"] = supporting_reference_records
        term["provenance"].append(
            _make_provenance(
                source="derived_from_ke_metadata",
                field=source_field,
                transformation="phase3_summary_applicability_consistency_heuristic",
                confidence="moderate" if evidence_call in {"high", "moderate"} else "low",
            )
        )
        results.append(term)
    return results


def _build_shared_ker_applicability_terms(
    upstream_record: dict[str, Any] | None,
    downstream_record: dict[str, Any] | None,
    *,
    field: str,
    source_field: str,
) -> list[dict[str, Any]]:
    if not upstream_record or not downstream_record:
        return []

    upstream_values = _extract_record_values(upstream_record, field)
    downstream_values = set(_extract_record_values(downstream_record, field))
    shared_values = [value for value in upstream_values if value in downstream_values]
    supporting_references = _normalize_reference_records(
        [
            *(upstream_record.get("references", []) or []),
            *(downstream_record.get("references", []) or []),
        ]
    )
    reference_count = _get_reference_count(supporting_references)
    results: list[dict[str, Any]] = []
    for value in shared_values:
        evidence_call = "moderate" if reference_count else "low"
        rationale = (
            "Derived from applicability terms shared by both upstream and downstream key events, with supporting references carried forward from the linked key events."
            if reference_count
            else "Derived from applicability terms shared by both upstream and downstream key events. The current RDF export does not expose direct KER-level applicability evidence strength."
        )
        term = _build_applicability_term(
            value,
            source_field=source_field,
            source="derived_from_shared_ke_metadata",
            evidence_call=evidence_call,
            rationale=rationale,
        )
        if term is None:
            continue
        term["references"] = supporting_references
        term["provenance"].append(
            _make_provenance(
                source="derived_from_shared_ke_metadata",
                field=source_field,
                transformation="phase3_ker_applicability_intersection",
                confidence="moderate" if reference_count else "low",
            )
        )
        results.append(term)
    return results


def _derive_ker_applicability(
    upstream_record: dict[str, Any] | None,
    downstream_record: dict[str, Any] | None,
) -> dict[str, Any]:
    taxa = _build_shared_ker_applicability_terms(
        upstream_record,
        downstream_record,
        field="taxonomic_applicability",
        source_field="taxonomic_applicability",
    )
    life_stages = _build_shared_ker_applicability_terms(
        upstream_record,
        downstream_record,
        field="life_stage_applicability",
        source_field="life_stage_applicability",
    )
    sexes = _build_shared_ker_applicability_terms(
        upstream_record,
        downstream_record,
        field="sex_applicability",
        source_field="sex_applicability",
    )

    if upstream_record and downstream_record:
        summary_rationale = (
            "Derived conservatively from applicability terms shared by both upstream and downstream key events because direct KER-level applicability fields are not exposed in the current RDF export."
            if (taxa or life_stages or sexes)
            else "No shared upstream/downstream applicability terms were available to derive a conservative KER-level applicability summary."
        )
        transformation = "phase3_ker_applicability_intersection"
        confidence = "moderate" if (taxa or life_stages or sexes) else "low"
    else:
        summary_rationale = (
            "Upstream or downstream key event applicability metadata was unavailable, so no KER-level applicability intersection could be derived."
        )
        transformation = "phase3_ker_applicability_unavailable"
        confidence = "low"

    return {
        "taxa": taxa,
        "life_stages": life_stages,
        "sexes": sexes,
        "summary_rationale": summary_rationale,
        "provenance": [
            _make_provenance(
                source="derived_from_shared_ke_metadata",
                field="applicability",
                transformation=transformation,
                confidence=confidence,
            )
        ],
    }


def _build_stressor_term(stressor: dict[str, Any]) -> dict[str, Any]:
    chemical_identifier = stressor.get("chemical_iri") or (
        f"CAS:{stressor['casrn']}" if stressor.get("casrn") else stressor.get("stressor_id")
    )
    label = stressor.get("label") or stressor.get("casrn")
    return {
        "id": chemical_identifier,
        "label": label,
        "source_field": "stressor_chemicals",
        "stressor_id": stressor.get("stressor_id"),
        "chemical_iri": stressor.get("chemical_iri"),
        "casrn": stressor.get("casrn"),
        "provenance": [
            _make_provenance(
                source="aop_db_sparql",
                field="stressor_chemicals",
                transformation="normalized_for_oecd_phase2",
                confidence="moderate",
            )
        ],
    }


def _extract_title_segments(value: str | None) -> list[str]:
    if not value:
        return []
    segments = [_segment.strip() for _segment in re.split(r"[,;]+", value) if _segment.strip()]
    return segments


def _infer_action_label(record: dict[str, Any]) -> str | None:
    direction = record.get("direction_of_change")
    if direction:
        return str(direction)

    candidates = [
        *(_extract_title_segments(record.get("title"))[:1]),
        str(record.get("short_name") or ""),
    ]
    for candidate in candidates:
        normalized = candidate.strip().lower()
        if not normalized:
            continue
        if "activation" in normalized:
            return "activation"
        if "inhibition" in normalized or "inhibit" in normalized:
            return "inhibition"
        if "repression" in normalized or "repress" in normalized:
            return "repression"
        if "decreas" in normalized or normalized.startswith("loss"):
            return "decreased"
        if "increas" in normalized or normalized.startswith("gain"):
            return "increased"
    return None


def _action_term_from_record(record: dict[str, Any]) -> dict[str, Any] | None:
    direction = record.get("direction_of_change")
    if direction:
        return _build_ontology_term(
            str(direction),
            source_field="direction_of_change",
            transformation="normalized_for_oecd_phase2",
        )

    inferred = _infer_action_label(record)
    if not inferred:
        return None
    return _build_ontology_term(
        inferred,
        source_field="title_or_short_name",
        transformation="title_based_action_inference_phase2",
        confidence="low",
    )


def _derive_title_based_object_terms(record: dict[str, Any]) -> list[dict[str, Any]]:
    existing_labels = {
        str(value).lower()
        for value in (
            *(record.get("gene_identifiers", []) or []),
            *(record.get("protein_identifiers", []) or []),
        )
        if value
    }
    title = str(record.get("title") or "")
    short_name = str(record.get("short_name") or "")
    candidates: list[str] = []

    title_segments = _extract_title_segments(title)
    if len(title_segments) > 1:
        candidates.extend(title_segments[1:])

    short_candidate = re.sub(
        r"\b(activation|inhibition|repression|increase|increased|decrease|decreased)\b",
        "",
        short_name,
        flags=re.IGNORECASE,
    ).strip(" -_,;")
    if short_candidate and short_candidate.lower() not in {"", "activity"}:
        candidates.append(short_candidate)

    results: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", candidate).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen_labels or lowered in existing_labels:
            continue
        if len(cleaned) <= 2:
            continue
        seen_labels.add(lowered)
        term = _build_ontology_term(
            cleaned,
            source_field="title_derived_biological_object",
            transformation="title_segment_inference_phase2",
            confidence="low",
        )
        if term:
            results.append(term)
    return results


def _build_evidence_block(
    text: str | None,
    *,
    source_field: str,
    basis: str,
    source: str = "aop_wiki_rdf",
    heuristic_call: str | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "heuristic_call": heuristic_call or _extract_support_call(text),
        "basis": basis,
        "references": [],
        "provenance": [
            _make_provenance(
                source=source,
                field=source_field,
                transformation="phase1_evidence_block_normalization",
                confidence="moderate",
            )
        ],
    }


def _normalize_applicability_summary(
    summary: dict[str, Any],
    *,
    key_event_details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    key_event_details = key_event_details or []
    total = len(key_event_details)
    summary_rationale = (
        f"Aggregated from {total} key events because dedicated AOP-level applicability is not consistently exposed in the current RDF export. "
        "Evidence calls reflect cross-KE consistency and supporting references rather than a direct AOP-level applicability strength field."
        if total
        else None
    )
    return {
        "basis": summary.get("basis"),
        "taxa": _build_summary_applicability_terms(
            key_event_details,
            field="taxonomic_applicability",
            source_field="taxonomic_applicability",
        ),
        "life_stages": _build_summary_applicability_terms(
            key_event_details,
            field="life_stage_applicability",
            source_field="life_stage_applicability",
        ),
        "sexes": _build_summary_applicability_terms(
            key_event_details,
            field="sex_applicability",
            source_field="sex_applicability",
        ),
        "organs": _build_summary_applicability_terms(
            key_event_details,
            field="organ_context",
            source_field="organ_context",
        ),
        "cell_types": _build_summary_applicability_terms(
            key_event_details,
            field="cell_type_context",
            source_field="cell_type_context",
        ),
        "levels_of_biological_organization": [
            item
            for item in (
                _build_ontology_term(
                    value,
                    source_field="level_of_biological_organization",
                    transformation="normalized_for_oecd_phase1",
                )
                for value in summary.get("level_of_biological_organization", [])
            )
            if item
        ],
        "summary_rationale": summary_rationale,
        "provenance": [
            _make_provenance(
                source="derived_from_ke_metadata",
                field="applicability_summary",
                transformation="phase3_oecd_applicability_summary",
                confidence="moderate",
            )
        ],
    }


def _normalize_key_event_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized_references = _normalize_reference_records(record.get("references"))
    normalized["iri"] = record.get("iri") or _default_iri_for_identifier(record.get("id"))
    normalized["part_of_aops"] = [
        _normalize_link_record(item) for item in record.get("part_of_aops", [])
    ]
    normalized["event_components"] = {
        "biological_processes": [
            item
            for item in (
                _build_ontology_term(
                    value,
                    source_field="biological_processes",
                    transformation="normalized_for_oecd_phase1",
                )
                for value in record.get("biological_processes", [])
            )
            if item
        ],
        "biological_objects": [
            item
            for item in (
                [
                    _build_ontology_term(
                        value,
                        source_field="gene_identifiers",
                        transformation="normalized_for_oecd_phase1",
                    )
                    for value in record.get("gene_identifiers", [])
                ]
                + [
                    _build_ontology_term(
                        value,
                        source_field="protein_identifiers",
                        transformation="normalized_for_oecd_phase1",
                    )
                    for value in record.get("protein_identifiers", [])
                ]
                + _derive_title_based_object_terms(record)
            )
            if item
        ],
        "action": _action_term_from_record(record),
    }
    normalized["biological_context"] = {
        "organs": [
            item
            for item in (
                _build_direct_applicability_term(
                    value,
                    source_field="organ_context",
                    references=normalized_references,
                )
                for value in record.get("organ_context", [])
            )
            if item
        ],
        "cell_types": [
            item
            for item in (
                _build_direct_applicability_term(
                    value,
                    source_field="cell_type_context",
                    references=normalized_references,
                )
                for value in record.get("cell_type_context", [])
            )
            if item
        ],
        "level_of_biological_organization": _build_ontology_term(
            record.get("level_of_biological_organization"),
            source_field="level_of_biological_organization",
            transformation="normalized_for_oecd_phase1",
        ),
    }
    normalized["applicability"] = {
        "taxa": [
            item
            for item in (
                _build_direct_applicability_term(
                    value,
                    source_field="taxonomic_applicability",
                    references=normalized_references,
                )
                for value in record.get("taxonomic_applicability", [])
            )
            if item
        ],
        "life_stages": [
            item
            for item in (
                _build_direct_applicability_term(
                    value,
                    source_field="life_stage_applicability",
                    references=normalized_references,
                )
                for value in [record.get("life_stage_applicability")]
            )
            if item
        ],
        "sexes": [
            item
            for item in (
                _build_direct_applicability_term(
                    value,
                    source_field="sex_applicability",
                    references=normalized_references,
                )
                for value in [record.get("sex_applicability")]
            )
            if item
        ],
        "summary_rationale": (
            "Structured applicability terms were taken directly from KE metadata. "
            "Evidence calls reflect source presence and KE-level references rather than a direct OECD applicability strength field."
            if (
                record.get("taxonomic_applicability")
                or record.get("life_stage_applicability")
                or record.get("sex_applicability")
            )
            else None
        ),
        "provenance": [
            _make_provenance(
                source="aop_wiki_rdf",
                field="applicability",
                transformation="phase3_oecd_alignment_normalization",
                confidence="moderate",
            )
        ],
    }
    normalized["measurement_method_details"] = [
        item
        for item in (
            _build_measurement_method_detail(label)
            for label in record.get("measurement_methods", [])
        )
        if item
    ]
    normalized["mie_specific"] = None
    normalized["ao_specific"] = None
    normalized["references"] = normalized_references
    normalized["provenance"] = [
        _make_provenance(
            source="aop_wiki_rdf",
            field="get_key_event",
            transformation="phase3_oecd_alignment_normalization",
            confidence="moderate",
        )
    ]
    return normalized


def _normalize_ker_record(
    record: dict[str, Any],
    *,
    upstream_record: dict[str, Any] | None = None,
    downstream_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(record)
    normalized_references = _normalize_reference_records(record.get("references"))
    normalized["iri"] = record.get("iri") or _default_iri_for_identifier(record.get("id"))
    normalized["upstream"] = _normalize_link_record(record.get("upstream", {}))
    normalized["downstream"] = _normalize_link_record(record.get("downstream", {}))
    normalized["referenced_aops"] = [
        _normalize_link_record(item) for item in record.get("referenced_aops", [])
    ]
    normalized["applicability"] = _derive_ker_applicability(upstream_record, downstream_record)
    normalized["evidence_blocks"] = {
        "biological_plausibility": _build_evidence_block(
            record.get("biological_plausibility"),
            source_field="biological_plausibility",
            basis="Normalized from KER biological plausibility text.",
        ),
        "empirical_support": _build_evidence_block(
            record.get("empirical_support"),
            source_field="empirical_support",
            basis="Normalized from KER empirical support text.",
        ),
        "quantitative_understanding": _build_evidence_block(
            record.get("quantitative_understanding"),
            source_field="quantitative_understanding",
            basis="Normalized from KER quantitative understanding text.",
        ),
    }
    normalized["references"] = normalized_references
    normalized["provenance"] = [
        _make_provenance(
            source="aop_wiki_rdf",
            field="get_ker",
            transformation="phase3_oecd_alignment_normalization",
            confidence="moderate",
        )
    ]
    return normalized


def _normalize_aop_record(
    core_record: dict[str, Any],
    *,
    assessment_record: dict[str, Any] | None = None,
    stressor_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    record = dict(core_record)
    assessment_record = assessment_record or {}
    record["iri"] = core_record.get("iri") or assessment_record.get("iri") or _default_iri_for_identifier(core_record.get("id"))
    for key in ("created", "modified", "evidence_summary"):
        if record.get(key) is None and assessment_record.get(key) is not None:
            record[key] = assessment_record.get(key)
    record["molecular_initiating_events"] = [
        _normalize_link_record(item)
        for item in assessment_record.get("molecular_initiating_events", [])
    ]
    record["adverse_outcomes"] = [
        _normalize_link_record(item)
        for item in assessment_record.get("adverse_outcomes", [])
    ]
    record["stressors"] = [_build_stressor_term(item) for item in (stressor_records or [])]
    record["graph"] = None
    record["overall_applicability"] = {
        "basis": "Not yet exposed as a dedicated AOP-level field in the current RDF export. Placeholder retained for the OECD-aligned contract.",
        "taxa": [],
        "life_stages": [],
        "sexes": [],
        "organs": [],
        "cell_types": [],
        "levels_of_biological_organization": [],
        "summary_rationale": None,
        "provenance": [
            _make_provenance(
                source="aop_wiki_rdf",
                field="overall_applicability",
                transformation="placeholder_pending_aop_level_normalization",
                confidence="low",
            )
        ],
    }
    record["references"] = _normalize_reference_records(
        [
            *(core_record.get("references") or []),
            *(assessment_record.get("references") or []),
        ]
    )
    record["provenance"] = [
        _make_provenance(
            source="aop_wiki_rdf",
            field="get_aop",
            transformation="phase1_oecd_alignment_normalization",
            confidence="moderate",
        ),
        _make_provenance(
            source="aop_db_sparql",
            field="stressor_chemicals",
            transformation="phase2_stressor_enrichment",
            confidence="moderate" if stressor_records else "low",
        ),
    ]
    return record


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
    aop: dict[str, Any],
    key_event_details: list[dict[str, Any]],
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
        "essentiality_of_key_events": _build_essentiality_dimension(
            aop,
            key_event_details,
            ker_details,
        ),
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
    essentiality_call = confidence_dimensions["essentiality_of_key_events"]["heuristic_call"]
    limitations = []
    if essentiality_call == "not_assessed":
        limitations.append(
            "Key-event essentiality is not directly surfaced in the current RDF export, and no bounded heuristic cue was available to score it."
        )
    else:
        limitations.append(
            "Key-event essentiality is inferred heuristically from free-text cues and pathway structure because a dedicated RDF essentiality field is not currently exposed."
        )
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
        if dimension.get("heuristic_call") in {"not_assessed", "not_reported"}
    ]
    return {
        "status": "partial",
        "core_dimensions": list(confidence_dimensions.keys()),
        "missing_dimensions": missing_dimensions,
        "notes": [
            "Overall OECD confidence is defined by biological plausibility, empirical support, quantitative understanding, and KE essentiality.",
            "This tool approximates biological plausibility, empirical support, and quantitative understanding from KER text.",
            "KE essentiality is only reported directly when bounded textual or pathway heuristics are available; the current RDF export does not expose a dedicated structured essentiality field.",
        ],
    }


async def _get_key_event_if_available(adapter: Any, key_event_id: str | None) -> dict[str, Any] | None:
    if not key_event_id:
        return None
    return await adapter.get_key_event(key_event_id)


def _enumerate_mie_to_ao_paths(
    mie_ids: list[str],
    ao_ids: list[str],
    ker_details: list[dict[str, Any]],
    *,
    max_paths: int = 64,
) -> list[list[str]]:
    target_ids = set(ao_ids)
    adjacency: dict[str, list[str]] = {}
    event_ids: set[str] = set()
    for record in ker_details:
        upstream_id = record.get("upstream", {}).get("id")
        downstream_id = record.get("downstream", {}).get("id")
        if not upstream_id or not downstream_id:
            continue
        adjacency.setdefault(upstream_id, []).append(downstream_id)
        event_ids.add(upstream_id)
        event_ids.add(downstream_id)

    max_depth = max(1, len(event_ids) + 1)
    paths: list[list[str]] = []

    def dfs(current_id: str, visited: set[str], path: list[str]) -> None:
        if len(paths) >= max_paths or len(path) > max_depth:
            return
        if current_id in target_ids:
            paths.append(list(path))
            return
        for next_id in adjacency.get(current_id, []):
            if next_id in visited:
                continue
            visited.add(next_id)
            path.append(next_id)
            dfs(next_id, visited, path)
            path.pop()
            visited.remove(next_id)

    for mie_id in mie_ids:
        dfs(mie_id, {mie_id}, [mie_id])
        if len(paths) >= max_paths:
            break
    return paths


def _extract_essentiality_text_signal(texts: list[str | None]) -> tuple[str, int]:
    strong_hits = 0
    moderate_hits = 0
    for text in texts:
        if not text:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text.lower()):
            normalized = sentence.strip()
            if not normalized:
                continue
            if re.search(r"\bkey event essentiality\b", normalized):
                strong_hits += 1
                continue
            if re.search(
                r"\b(essential|necessary|required)\s+for\b.{0,80}\b(downstream|adverse outcome|response|effect|outcome|phenotype|steatosis|accumulation)\b",
                normalized,
            ):
                strong_hits += 1
                continue
            if (
                re.search(
                    r"\b(abolish|abrogate|prevent|block|eliminate)\w*\b.{0,30}\b(downstream|adverse outcome|response|effect|outcome|phenotype|steatosis|accumulation)\b",
                    normalized,
                )
                or re.search(
                    r"\b(downstream|adverse outcome|response|effect|outcome|phenotype|steatosis|accumulation)\b.{0,30}\b(abolish|abrogate|prevent|block|eliminate)\w*\b",
                    normalized,
                )
            ):
                strong_hits += 1
                continue
            if (
                re.search(
                    r"\b(attenuat|reduc|partial)\w*\b.{0,20}\b(downstream|adverse outcome|response|effect|outcome|phenotype|steatosis|accumulation)\b",
                    normalized,
                )
                or re.search(
                    r"\b(downstream|adverse outcome|response|effect|outcome|phenotype|steatosis|accumulation)\b.{0,20}\b(attenuat|reduc|partial)\w*\b",
                    normalized,
                )
                or "supports essentiality" in normalized
            ):
                moderate_hits += 1
    if strong_hits:
        return "strong", strong_hits
    if moderate_hits:
        return "moderate", moderate_hits
    return "not_reported", 0


def _build_essentiality_dimension(
    aop: dict[str, Any],
    key_event_details: list[dict[str, Any]],
    ker_details: list[dict[str, Any]],
) -> dict[str, Any]:
    mie_ids = [
        item.get("id")
        for item in aop.get("molecular_initiating_events", [])
        if item.get("id")
    ]
    ao_ids = [
        item.get("id")
        for item in aop.get("adverse_outcomes", [])
        if item.get("id")
    ]
    if not mie_ids or not ao_ids:
        return {
            "heuristic_call": "not_assessed",
            "coverage": {"present": 0, "total": len(key_event_details)},
            "basis": "MIE or AO anchors were unavailable, so no bounded KE-essentiality heuristic could be derived from pathway structure.",
            "oecd_dimension": True,
            "provenance": [
                _make_provenance(
                    source="derived_from_aop_structure",
                    field="essentiality_of_key_events",
                    transformation="phase3_essentiality_unavailable",
                    confidence="low",
                )
            ],
        }

    paths = _enumerate_mie_to_ao_paths(mie_ids, ao_ids, ker_details)
    all_path_nodes = [
        {
            node
            for node in path[1:-1]
            if node not in set(mie_ids) and node not in set(ao_ids)
        }
        for path in paths
    ]
    shared_internal_key_events = (
        sorted(set.intersection(*all_path_nodes)) if all_path_nodes else []
    )
    text_signal, cue_count = _extract_essentiality_text_signal(
        [
            aop.get("evidence_summary"),
            *(record.get("biological_plausibility") for record in ker_details),
            *(record.get("empirical_support") for record in ker_details),
            *(record.get("quantitative_understanding") for record in ker_details),
        ]
    )

    if text_signal == "strong" and paths:
        heuristic_call = "moderate"
        basis = (
            f"Derived heuristically from {cue_count} essentiality-like text cue(s) plus {len(paths)} observed MIE-to-AO path(s). "
            "The current RDF export does not expose a dedicated KE-essentiality field, so this remains a conservative heuristic."
        )
        confidence = "moderate"
    elif text_signal == "moderate" and paths:
        heuristic_call = "low"
        basis = (
            f"Derived heuristically from {cue_count} moderate essentiality-like text cue(s) across {len(paths)} observed MIE-to-AO path(s). "
            "This is weaker than a direct OECD essentiality assessment."
        )
        confidence = "low"
    elif shared_internal_key_events:
        heuristic_call = "not_assessed"
        basis = (
            f"No explicit essentiality wording was surfaced, although {len(shared_internal_key_events)} internal key event(s) lie on every observed MIE-to-AO path. "
            "Path structure alone is retained as context but is not sufficient to assign an OECD-style essentiality score."
        )
        confidence = "low"
    else:
        heuristic_call = "not_assessed"
        basis = (
            "Key-event essentiality is not directly surfaced in the current RDF export, and no bounded combination of text evidence plus path support was available to score it."
        )
        confidence = "low"

    return {
        "heuristic_call": heuristic_call,
        "coverage": {
            "present": cue_count if cue_count else len(shared_internal_key_events),
            "total": len(key_event_details),
        },
        "basis": basis,
        "oecd_dimension": True,
        "heuristic_inputs": {
            "text_signal": text_signal,
            "cue_count": cue_count,
            "path_count": len(paths),
            "shared_internal_key_events": shared_internal_key_events,
            "mie_count": len(mie_ids),
            "ao_count": len(ao_ids),
        },
        "provenance": [
            _make_provenance(
                source="derived_from_aop_structure",
                field="essentiality_of_key_events",
                transformation="phase3_essentiality_text_and_path_heuristic",
                confidence=confidence,
            )
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
