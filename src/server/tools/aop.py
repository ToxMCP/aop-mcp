"""Tool handlers wiring domain services to MCP."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.instrumentation.audit import (
    tool_call_audit_log,
    verify_draft_integrity,
)
from src.server.config.settings import get_settings
from src.adapters import CompToxError
from src.server.dependencies import (
    get_draft_store,
    get_aop_db_adapter,
    get_aop_wiki_adapter,
    get_comptox_client,
    get_semantic_tools,
    get_write_tools,
)
from src.services.registry_handoff import (
    build_imported_registry_support_summary,
    build_registry_handoff_review,
)
from src.services.draft_store import compute_provenance_checksum
from src.services.publish import LinearDocumentPlanner
from src.tools.write import (
    DraftApplicability,
    KeyEventPayload,
    KeyEventRelationshipPayload,
    StressorLinkPayload,
    is_governed_ke_essentiality,
    normalize_key_event_attributes,
)
from src.tools import validate_payload
from src.semantic.mechanism_roles import classify_key_event_role, summarize_mechanism_roles


class SearchAopsInput(BaseModel):
    text: Optional[str] = None
    limit: int = Field(default=25, ge=1, le=100)


async def search_aops(params: SearchAopsInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    results = await adapter.search_aops(text=params.text, limit=params.limit)
    payload = {"results": results}
    validate_payload(payload, namespace="read", name="search_aops.response.schema")
    return payload


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
    payload = {"results": items}
    validate_payload(payload, namespace="read", name="list_key_events.response.schema")
    return payload


class ListKersInput(BaseModel):
    aop_id: str


async def list_kers(params: ListKersInput) -> dict[str, Any]:
    adapter = get_aop_wiki_adapter()
    items = await adapter.list_kers(params.aop_id)
    payload = {"results": items}
    validate_payload(payload, namespace="read", name="list_kers.response.schema")
    return payload


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
    assay_cutoff_ordering = await _build_assay_cutoff_ordering_for_get_ker(
        raw_record,
        upstream_record=upstream_record,
        downstream_record=downstream_record,
    )
    record = _normalize_ker_record(
        raw_record,
        upstream_record=upstream_record,
        downstream_record=downstream_record,
        assay_cutoff_ordering=assay_cutoff_ordering,
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
    payload = {"aop": source_aop, "results": related}
    validate_payload(payload, namespace="read", name="get_related_aops.response.schema")
    return payload


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

    key_event_lookup = {
        record["id"]: record for record in key_event_details if record.get("id")
    }
    assay_cutoff_ordering_records = await _build_assay_cutoff_ordering_records(
        params.aop_id,
        key_event_details=key_event_details,
        ker_details=ker_details,
    )
    key_event_summaries = [_summarize_key_event(record) for record in key_event_details]
    mechanism_role_summary = summarize_mechanism_roles(key_event_details)
    ker_assessments = [
        _summarize_ker(
            record,
            key_event_lookup=key_event_lookup,
            assay_cutoff_ordering=assay_cutoff_ordering_records[index]
            if index < len(assay_cutoff_ordering_records)
            else None,
        )
        for index, record in enumerate(ker_details)
    ]
    coverage = _build_assessment_coverage(key_event_details, ker_details)
    if assay_cutoff_ordering_records:
        coverage["kers_with_assay_cutoff_ordering"] = sum(
            1
            for record in assay_cutoff_ordering_records
            if record.get("supporting_chemical_count", 0) > 0
        )
        coverage["assay_cutoff_ordering_supporting_chemicals"] = sum(
            record.get("supporting_chemical_count", 0)
            for record in assay_cutoff_ordering_records
        )
    applicability_summary = _build_applicability_summary(key_event_details)
    confidence_dimensions = _build_confidence_dimensions(
        aop,
        key_event_details,
        ker_details,
    )
    supplemental_signals = _build_supplemental_signals(
        overall_evidence=aop.get("evidence_summary"),
        citation_concordance_records=[
            item["citation_concordance"] for item in ker_assessments if item.get("citation_concordance")
        ],
        assay_cutoff_ordering_records=[
            item["assay_cutoff_ordering"] for item in ker_assessments if item.get("assay_cutoff_ordering")
        ],
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
    if (
        supplemental_signals.get("citation_concordance_signal", {}).get("heuristic_call")
        != "not_reported"
    ):
        rationale.append(
            "Supplemental citation concordance heuristic found shared or evaluable KE reference overlap for "
            f"{supplemental_signals['citation_concordance_signal']['coverage']['present']}/{coverage['ker_count']} KERs."
        )
    if (
        supplemental_signals.get("assay_cutoff_ordering_signal", {}).get("heuristic_call")
        != "not_reported"
    ):
        rationale.append(
            "Supplemental assay-cutoff ordering heuristic found evaluable upstream/downstream assay-cutoff comparisons for "
            f"{supplemental_signals['assay_cutoff_ordering_signal']['coverage']['present']}/{coverage['ker_count']} KERs."
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
        "mechanism_role_summary": mechanism_role_summary,
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
    payload = {
        "aop_id": _normalize_aop_element_id(params.aop_id),
        "source_event_id": source_event_id,
        "target_event_id": target_event_id,
        "path_count": len(paths),
        "results": paths,
    }
    validate_payload(payload, namespace="read", name="find_paths_between_events.response.schema")
    return payload


class MapChemicalInput(BaseModel):
    cas: Optional[str] = None
    name: Optional[str] = None

    @model_validator(mode="after")
    def ensure_identifier(self) -> "MapChemicalInput":
        if not (self.cas or self.name):
            raise ValueError("Provide at least one identifier: cas or name")
        return self


async def map_chemical_to_aops(params: MapChemicalInput) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    records = await adapter.map_chemical_to_aops(
        cas=params.cas,
        name=params.name,
    )
    payload = {"results": records}
    validate_payload(payload, namespace="read", name="map_chemical_to_aops.response.schema")
    return payload


class MapAssayInput(BaseModel):
    assay_id: str

    @model_validator(mode="after")
    def reject_explicit_aop_identifiers(self) -> "MapAssayInput":
        assay_id = self.assay_id.strip()
        if re.fullmatch(r"(?i)aop:\d+", assay_id) or re.fullmatch(
            r"(?i)https?://(?:www\.)?identifiers\.org/aop/\d+/?",
            assay_id,
        ):
            raise ValueError(
                "map_assay_to_aops expects an assay identifier, not an AOP identifier. "
                "Use get_assays_for_aop for one AOP ID or get_assays_for_aops for multiple AOP IDs."
            )
        self.assay_id = assay_id
        return self


async def map_assay_to_aops(params: MapAssayInput) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    records = await adapter.map_assay_to_aops(params.assay_id)
    payload = {"results": records}
    validate_payload(payload, namespace="read", name="map_assay_to_aops.response.schema")
    return payload


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
    payload = {
        "key_event": key_event,
        **assay_search,
    }
    validate_payload(payload, namespace="read", name="search_assays_for_key_event.response.schema")
    return payload


class ListAssaysForAopInput(BaseModel):
    aop_id: str
    limit: int = Field(default=25, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def list_assays_for_aop(params: ListAssaysForAopInput) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    payload = await adapter.list_assays_for_aop_with_diagnostics(
        params.aop_id,
        limit=params.limit,
        min_hitcall=params.min_hitcall,
    )
    validate_payload(payload, namespace="read", name="list_assays_for_aop.response.schema")
    return payload


class GetAssaysForAopInput(ListAssaysForAopInput):
    pass


async def get_assays_for_aop(params: GetAssaysForAopInput) -> dict[str, Any]:
    return await list_assays_for_aop(
        ListAssaysForAopInput.model_validate(params.model_dump())
    )


class DiscoverOrphanStressorsForAopInput(BaseModel):
    aop_id: str
    assay_limit: int = Field(default=10, ge=1, le=25)
    per_assay_chemical_limit: int = Field(default=25, ge=1, le=100)
    limit: int = Field(default=25, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def discover_orphan_stressors_for_aop(
    params: DiscoverOrphanStressorsForAopInput,
) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    payload = await adapter.discover_orphan_stressors_for_aop_with_diagnostics(
        params.aop_id,
        assay_limit=params.assay_limit,
        per_assay_chemical_limit=params.per_assay_chemical_limit,
        limit=params.limit,
        min_hitcall=params.min_hitcall,
    )
    validate_payload(
        payload,
        namespace="read",
        name="discover_orphan_stressors_for_aop.response.schema",
    )
    return payload


class DiscoverOrphanStressorsForAopsInput(BaseModel):
    aop_ids: list[str]
    limit: int = Field(default=25, ge=1, le=100)
    per_aop_limit: int = Field(default=10, ge=1, le=25)
    per_assay_chemical_limit: int = Field(default=25, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def ensure_aop_ids(self) -> "DiscoverOrphanStressorsForAopsInput":
        if not self.aop_ids:
            raise ValueError("Provide at least one aop_id")
        return self


async def discover_orphan_stressors_for_aops(
    params: DiscoverOrphanStressorsForAopsInput,
) -> dict[str, Any]:
    adapter = get_aop_db_adapter()
    payload = await adapter.discover_orphan_stressors_for_aops_with_diagnostics(
        params.aop_ids,
        limit=params.limit,
        per_aop_limit=params.per_aop_limit,
        per_assay_chemical_limit=params.per_assay_chemical_limit,
        min_hitcall=params.min_hitcall,
    )
    validate_payload(
        payload,
        namespace="read",
        name="discover_orphan_stressors_for_aops.response.schema",
    )
    return payload


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
    payload = await adapter.list_assays_for_aops_with_diagnostics(
        params.aop_ids,
        limit=params.limit,
        per_aop_limit=params.per_aop_limit,
        min_hitcall=params.min_hitcall,
    )
    validate_payload(payload, namespace="read", name="list_assays_for_aops.response.schema")
    return payload


class GetAssaysForAopsInput(ListAssaysForAopsInput):
    pass


async def get_assays_for_aops(params: GetAssaysForAopsInput) -> dict[str, Any]:
    return await list_assays_for_aops(
        ListAssaysForAopsInput.model_validate(params.model_dump())
    )


class ListAssaysForQueryInput(BaseModel):
    query: str
    search_limit: int = Field(default=25, ge=1, le=100)
    aop_limit: int = Field(default=10, ge=1, le=100)
    limit: int = Field(default=25, ge=1, le=100)
    per_aop_limit: int = Field(default=15, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def list_assays_for_query(params: ListAssaysForQueryInput) -> dict[str, Any]:
    selected_aops, records, diagnostics = await _resolve_assays_from_query_with_diagnostics(
        params.query,
        search_limit=params.search_limit,
        aop_limit=params.aop_limit,
        limit=params.limit,
        per_aop_limit=params.per_aop_limit,
        min_hitcall=params.min_hitcall,
    )
    payload = {
        "query": params.query,
        "selected_aops": selected_aops,
        "results": records,
        "diagnostics": diagnostics,
    }
    validate_payload(payload, namespace="read", name="list_assays_for_query.response.schema")
    return payload


class DiscoverOrphanStressorsForQueryInput(BaseModel):
    query: str
    search_limit: int = Field(default=25, ge=1, le=100)
    aop_limit: int = Field(default=10, ge=1, le=100)
    limit: int = Field(default=25, ge=1, le=100)
    per_aop_limit: int = Field(default=10, ge=1, le=25)
    per_assay_chemical_limit: int = Field(default=25, ge=1, le=100)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def discover_orphan_stressors_for_query(
    params: DiscoverOrphanStressorsForQueryInput,
) -> dict[str, Any]:
    selected_aops, records, diagnostics = await _resolve_orphans_from_query_with_diagnostics(
        params.query,
        search_limit=params.search_limit,
        aop_limit=params.aop_limit,
        limit=params.limit,
        per_aop_limit=params.per_aop_limit,
        per_assay_chemical_limit=params.per_assay_chemical_limit,
        min_hitcall=params.min_hitcall,
    )
    payload = {
        "query": params.query,
        "selected_aops": selected_aops,
        "results": records,
        "diagnostics": diagnostics,
    }
    validate_payload(
        payload,
        namespace="read",
        name="discover_orphan_stressors_for_query.response.schema",
    )
    return payload


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

    payload = {
        "format": params.format,
        "filename": _build_export_filename(params.format, query=params.query, aop_ids=params.aop_ids or []),
        "row_count": len(records),
        "selected_aops": selected_aops,
        "content": _serialize_assay_rows(records, params.format),
    }
    validate_payload(payload, namespace="read", name="export_assays_table.response.schema")
    return payload


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


async def _resolve_assays_from_query_with_diagnostics(
    query: str,
    *,
    search_limit: int,
    aop_limit: int,
    limit: int,
    per_aop_limit: int,
    min_hitcall: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    wiki_adapter = get_aop_wiki_adapter()
    search_results = await wiki_adapter.search_aops(text=query, limit=search_limit)
    selected_aops = search_results[:aop_limit]
    selected_aop_ids = [row["id"] for row in selected_aops if row.get("id")]

    diagnostics = {
        "query": query,
        "matched_aop_count": len(search_results),
        "selected_aop_count": len(selected_aops),
        "returned_assay_count": 0,
        "per_aop": [],
        "warnings": [],
    }
    if len(selected_aops) < len(search_results):
        diagnostics["warnings"].append(
            f"Selected the top {len(selected_aops)} AOP matches from {len(search_results)} query results."
        )
    if len(selected_aop_ids) < len(selected_aops):
        diagnostics["warnings"].append(
            "Some selected AOP search results did not include an identifier and were skipped during assay lookup."
        )
    if not selected_aop_ids:
        diagnostics["warnings"].append("No AOP identifiers were available for assay lookup.")
        return selected_aops, [], diagnostics

    db_adapter = get_aop_db_adapter()
    assay_report = await db_adapter.list_assays_for_aops_with_diagnostics(
        selected_aop_ids,
        limit=limit,
        per_aop_limit=per_aop_limit,
        min_hitcall=min_hitcall,
    )
    diagnostics["returned_assay_count"] = len(assay_report["results"])
    diagnostics["per_aop"] = assay_report["diagnostics"]["per_aop"]
    diagnostics["warnings"].extend(assay_report["diagnostics"]["warnings"])
    diagnostics["warnings"] = list(dict.fromkeys(diagnostics["warnings"]))
    return selected_aops, assay_report["results"], diagnostics


async def _resolve_orphans_from_query_with_diagnostics(
    query: str,
    *,
    search_limit: int,
    aop_limit: int,
    limit: int,
    per_aop_limit: int,
    per_assay_chemical_limit: int,
    min_hitcall: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    wiki_adapter = get_aop_wiki_adapter()
    search_results = await wiki_adapter.search_aops(text=query, limit=search_limit)
    selected_aops = search_results[:aop_limit]
    selected_aop_ids = [row["id"] for row in selected_aops if row.get("id")]

    diagnostics = {
        "query": query,
        "matched_aop_count": len(search_results),
        "selected_aop_count": len(selected_aops),
        "returned_candidate_count": 0,
        "per_aop": [],
        "warnings": [],
    }
    if len(selected_aops) < len(search_results):
        diagnostics["warnings"].append(
            f"Selected the top {len(selected_aops)} AOP matches from {len(search_results)} query results."
        )
    if len(selected_aop_ids) < len(selected_aops):
        diagnostics["warnings"].append(
            "Some selected AOP search results did not include an identifier and were skipped during orphan-candidate discovery."
        )
    if not selected_aop_ids:
        diagnostics["warnings"].append("No AOP identifiers were available for orphan-candidate discovery.")
        return selected_aops, [], diagnostics

    db_adapter = get_aop_db_adapter()
    orphan_report = await db_adapter.discover_orphan_stressors_for_aops_with_diagnostics(
        selected_aop_ids,
        limit=limit,
        per_aop_limit=per_aop_limit,
        per_assay_chemical_limit=per_assay_chemical_limit,
        min_hitcall=min_hitcall,
    )
    diagnostics["returned_candidate_count"] = len(orphan_report["results"])
    diagnostics["per_aop"] = orphan_report["diagnostics"]["per_aop"]
    diagnostics["warnings"].extend(orphan_report["diagnostics"]["warnings"])
    diagnostics["warnings"] = list(dict.fromkeys(diagnostics["warnings"]))
    return selected_aops, orphan_report["results"], diagnostics


def _build_export_filename(format_name: str, *, query: str | None, aop_ids: list[str]) -> str:
    if query:
        return f"assays_{_slugify(query)}.{format_name}"
    return f"assays_{len(aop_ids)}_aops.{format_name}"


def _build_draft_review_artifact_filename(
    format_name: str,
    *,
    draft_id: str,
    artifact_profile: Literal["review", "publication"] = "review",
) -> str:
    suffix = "md" if format_name == "markdown" else "json"
    slug = _slugify(draft_id)
    if artifact_profile == "publication" and not slug.endswith("_publication"):
        slug = f"{slug}_publication"
    return f"draft_review_{slug}.{suffix}"


def _normalize_artifact_subdirectory(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().replace("\\", "/").strip("/")
    if not normalized:
        return None
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("subdirectory must be a relative path without empty, '.' or '..' segments")
    return "/".join(parts)


def _validate_artifact_filename(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip():
        raise ValueError("filename must not be empty")
    if value != Path(value).name or any(sep in value for sep in ("/", "\\")):
        raise ValueError("filename must be a plain file name without directory separators")
    if value in {".", ".."}:
        raise ValueError("filename must not be '.' or '..'")
    return value


def _resolve_artifact_output_directory(subdirectory: str | None = None) -> Path:
    settings = get_settings()
    root = Path(settings.artifact_output_dir).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    target_dir = root / "draft_reviews"
    if subdirectory:
        target_dir = target_dir.joinpath(*subdirectory.split("/"))
    return target_dir.resolve()


def _artifact_metadata_path(artifact_path: Path) -> Path:
    return artifact_path.parent / f"{artifact_path.name}.meta.json"


def _isoformat_utc(value: float | datetime) -> str:
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc)
    else:
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _current_utc_timestamp() -> str:
    return _isoformat_utc(datetime.now(timezone.utc))


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


def _render_draft_review_artifact_markdown(bundle: dict[str, Any]) -> str:
    return _render_draft_review_artifact_markdown_for_profile(
        bundle,
        artifact_profile="review",
    )


def _render_draft_review_artifact_markdown_for_profile(
    bundle: dict[str, Any],
    *,
    artifact_profile: Literal["review", "publication"],
    evidence_gaps: dict[str, Any] | None = None,
) -> str:
    if artifact_profile == "publication":
        return _render_publication_draft_review_artifact_markdown(
            bundle,
            evidence_gaps=evidence_gaps,
        )

    return _render_review_draft_review_artifact_markdown(
        bundle,
        evidence_gaps=evidence_gaps,
    )


def _render_review_draft_review_artifact_markdown(
    bundle: dict[str, Any],
    *,
    evidence_gaps: dict[str, Any] | None = None,
) -> str:
    draft = bundle["draft"]
    bundle_summary = bundle["bundle_summary"]
    validation = bundle["validation"]
    quantitative_review = bundle["quantitative_review"]
    chemical_trace = bundle.get("chemical_trace")

    lines = [
        f"# Draft Review Artifact: {draft.get('title') or bundle['draft_id']}",
        "",
        "## Draft Review Summary",
        f"- Draft ID: {bundle['draft_id']}",
        f"- Version ID: {bundle['version_id']}",
        f"- Adverse outcome: {draft.get('adverse_outcome') or 'Not recorded'}",
        f"- Ready for review: {_yes_no(bundle_summary['ready_for_review'])}",
        f"- Validator errors: {bundle_summary['validator_error_count']}",
        f"- Validator warnings: {bundle_summary['validator_warning_count']}",
        f"- Assessable KER quantitative reviews: {bundle_summary['assay_cutoff_assessable_relationship_count']}",
        f"- Discordant KER quantitative reviews: {bundle_summary['assay_cutoff_discordant_relationship_count']}",
        f"- Chemical trace included: {_yes_no(bundle_summary['chemical_trace_included'])}",
        "",
        "## Validation Findings",
    ]

    failed_checks = [item for item in validation["results"] if item["status"] == "fail"]
    if failed_checks:
        for item in failed_checks:
            lines.append(f"- [{item['severity']}] `{item['id']}`: {item['message']}")
    else:
        lines.append("- No failing validation checks.")

    quantitative_summary = quantitative_review["summary"]
    lines.extend(
        [
            "",
            "## Quantitative Review",
            f"- Linked stressors: {quantitative_summary['linked_stressor_count']}",
            f"- Searchable stressors: {quantitative_summary['searchable_stressor_count']}",
            f"- Assessable relationships: {quantitative_summary['assessable_relationship_count']}",
            f"- Concordant relationships: {quantitative_summary['concordant_relationship_count']}",
            f"- Discordant relationships: {quantitative_summary['discordant_relationship_count']}",
        ]
    )

    for relationship in quantitative_review["relationships"]:
        ordering = relationship["assay_cutoff_ordering"]
        lines.extend(
            [
                "",
                f"### {relationship['id']} ({relationship['source']} -> {relationship['target']})",
                f"- Assay cutoff ordering: {relationship['assay_cutoff_ordering_call']}",
                f"- Supporting chemicals: {relationship['assay_cutoff_supporting_chemical_count']}",
                f"- Basis: {ordering['basis']}",
            ]
        )
        if ordering["supporting_chemicals"]:
            lines.append("")
            lines.append("| Chemical | DTXSID | CAS RN | Upstream cutoff | Downstream cutoff | Ordering |")
            lines.append("| --- | --- | --- | ---: | ---: | --- |")
            for chemical in ordering["supporting_chemicals"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            chemical.get("preferred_name") or "",
                            chemical.get("dtxsid") or "",
                            chemical.get("casrn") or "",
                            _format_optional_number(chemical.get("upstream_best_activity_cutoff")),
                            _format_optional_number(chemical.get("downstream_best_activity_cutoff")),
                            chemical.get("ordering") or "",
                        ]
                    )
                    + " |"
                )

    lines.extend(["", "## Chemical Trace"])
    if chemical_trace is None:
        lines.append("- No chemical trace was requested.")
    else:
        chemical = chemical_trace["chemical"]
        summary = chemical_trace["summary"]
        lines.extend(
            [
                f"- Chemical: {chemical.get('preferred_name') or chemical.get('dtxsid') or 'Unknown'}",
                f"- DTXSID: {chemical.get('dtxsid') or 'Not resolved'}",
                f"- Active key events: {summary['active_key_event_count']}",
                f"- Inactive key events: {summary['inactive_key_event_count']}",
                f"- Traced key events: {summary['traced_key_event_count']}",
            ]
        )
        for key_event in chemical_trace["key_events"]:
            lines.append(
                f"- {key_event['id']}: {key_event['activity_state']} "
                f"(max_hitcall={_format_optional_number(key_event['max_hitcall'])}, "
                f"best_cutoff={_format_optional_number(key_event['best_activity_cutoff'])})"
            )

    lines.extend(["", "## Evidence Gaps"])
    if evidence_gaps is None:
        lines.append("- Evidence-gap review was not included for this artifact.")
    else:
        gap_summary = evidence_gaps["summary"]
        lines.extend(
            [
                f"- Total gaps: {gap_summary['total_gap_count']}",
                f"- Blocking gaps: {gap_summary['blocking_gap_count']}",
                f"- Advisory gaps: {gap_summary['advisory_gap_count']}",
                f"- KE assay-mapping gaps: {gap_summary['assay_mapping_gap_count']}",
            ]
        )
        if evidence_gaps["global_gaps"]:
            lines.extend(["", "### Global Gaps"])
            for gap in evidence_gaps["global_gaps"]:
                lines.append(f"- [{gap['severity']}] `{gap['id']}`: {gap['detail']}")
        key_event_gap_rows = [item for item in evidence_gaps["key_events"] if item["gaps"]]
        if key_event_gap_rows:
            lines.extend(["", "### Key Event Gaps"])
            for item in key_event_gap_rows:
                lines.append(
                    f"- `{item['id']}` ({item['title'] or 'Untitled'}): "
                    + "; ".join(gap["title"] for gap in item["gaps"])
                )
        relationship_gap_rows = [item for item in evidence_gaps["relationships"] if item["gaps"]]
        if relationship_gap_rows:
            lines.extend(["", "### Relationship Gaps"])
            for item in relationship_gap_rows:
                lines.append(
                    f"- `{item['id']}` ({item['source']} -> {item['target']}): "
                    + "; ".join(gap["title"] for gap in item["gaps"])
                )
        stressor_gap_rows = [item for item in evidence_gaps["stressors"] if item["gaps"]]
        if stressor_gap_rows:
            lines.extend(["", "### Stressor Gaps"])
            for item in stressor_gap_rows:
                lines.append(
                    f"- `{item['stressor_id'] or item['label'] or 'Unknown stressor'}`: "
                    + "; ".join(gap["title"] for gap in item["gaps"])
                )

    _append_external_support_section(lines, bundle.get("external_support"))

    lines.extend(["", "## Recommended Next Actions"])
    recommendations = (
        evidence_gaps["recommendations"]
        if evidence_gaps is not None
        else _build_draft_review_recommendations(bundle)
    )
    for recommendation in recommendations:
        lines.append(f"- {recommendation}")

    lines.extend(["", "## Limitations"])
    if bundle["limitations"]:
        for limitation in bundle["limitations"]:
            lines.append(f"- {limitation}")
    else:
        lines.append("- No additional limitations were reported.")

    return "\n".join(lines) + "\n"


def _render_publication_draft_review_artifact_markdown(
    bundle: dict[str, Any],
    *,
    evidence_gaps: dict[str, Any] | None = None,
) -> str:
    draft = bundle["draft"]
    bundle_summary = bundle["bundle_summary"]
    validation = bundle["validation"]
    quantitative_review = bundle["quantitative_review"]
    chemical_trace = bundle.get("chemical_trace")

    failed_errors = [
        item
        for item in validation["results"]
        if item["status"] == "fail" and item["severity"] == "error"
    ]
    failed_warnings = [
        item
        for item in validation["results"]
        if item["status"] == "fail" and item["severity"] == "warning"
    ]
    passed_checks = [item for item in validation["results"] if item["status"] == "pass"]
    quantitative_summary = quantitative_review["summary"]
    recommendations = (
        evidence_gaps["recommendations"]
        if evidence_gaps is not None
        else _build_draft_review_recommendations(bundle)
    )

    disposition = (
        "Ready for external scientific review"
        if bundle_summary["ready_for_review"]
        else "Needs revision before external scientific review"
    )

    lines = [
        f"# Scientific Draft Review: {draft.get('title') or bundle['draft_id']}",
        "",
        "## Executive Summary",
        f"- Disposition: {disposition}",
        f"- Draft ID: {bundle['draft_id']}",
        f"- Version ID: {bundle['version_id']}",
        f"- Adverse outcome: {draft.get('adverse_outcome') or 'Not recorded'}",
        f"- Validation score: {validation['summary']['score']}",
        f"- Blocking validation findings: {bundle_summary['validator_error_count']}",
        f"- Non-blocking review warnings: {bundle_summary['validator_warning_count']}",
        f"- Assessable quantitative KER reviews: {bundle_summary['assay_cutoff_assessable_relationship_count']}",
        f"- Discordant quantitative KER reviews: {bundle_summary['assay_cutoff_discordant_relationship_count']}",
        f"- Chemical activity overlay included: {_yes_no(bundle_summary['chemical_trace_included'])}",
        "",
        "## Draft Context",
        "| Field | Value |",
        "| --- | --- |",
        f"| Draft title | {draft.get('title') or bundle['draft_id']} |",
        f"| Draft ID | {bundle['draft_id']} |",
        f"| Version ID | {bundle['version_id']} |",
        f"| Adverse outcome | {draft.get('adverse_outcome') or 'Not recorded'} |",
        f"| Key events in quantitative review scope | {quantitative_summary['key_event_count']} |",
        f"| Relationships in quantitative review scope | {quantitative_summary['relationship_count']} |",
        f"| Linked stressors | {quantitative_summary['linked_stressor_count']} |",
        "",
        "## Review Findings",
        f"- Blocking findings: {len(failed_errors)}",
        f"- Advisory findings: {len(failed_warnings)}",
        f"- Passed checks: {len(passed_checks)}",
    ]

    if failed_errors:
        lines.extend(["", "### Blocking Findings"])
        for item in failed_errors:
            lines.append(f"- `{item['id']}`: {item['message']}")

    if failed_warnings:
        lines.extend(["", "### Advisory Findings"])
        for item in failed_warnings:
            lines.append(f"- `{item['id']}`: {item['message']}")

    if not failed_errors and not failed_warnings:
        lines.extend(["", "- No failing validation findings were reported."])

    lines.extend(
        [
            "",
            "## Quantitative Evidence",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Searchable stressors | {quantitative_summary['searchable_stressor_count']} |",
            f"| Assessable relationships | {quantitative_summary['assessable_relationship_count']} |",
            f"| Concordant relationships | {quantitative_summary['concordant_relationship_count']} |",
            f"| Discordant relationships | {quantitative_summary['discordant_relationship_count']} |",
            f"| Supporting chemical observations | {quantitative_summary['supporting_chemical_count']} |",
        ]
    )

    if quantitative_review["relationships"]:
        lines.extend(
            [
                "",
                "| Relationship | Call | Supporting chemicals | Basis |",
                "| --- | --- | ---: | --- |",
            ]
        )
        for relationship in quantitative_review["relationships"]:
            ordering = relationship["assay_cutoff_ordering"]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{relationship['id']} ({relationship['source']} -> {relationship['target']})",
                        relationship["assay_cutoff_ordering_call"],
                        str(relationship["assay_cutoff_supporting_chemical_count"]),
                        ordering["basis"],
                    ]
                )
                + " |"
            )

        detailed_relationships = [
            relationship
            for relationship in quantitative_review["relationships"]
            if relationship["assay_cutoff_ordering"]["supporting_chemicals"]
        ]
        if detailed_relationships:
            lines.extend(["", "### Supporting Chemical Details"])
            for relationship in detailed_relationships:
                ordering = relationship["assay_cutoff_ordering"]
                lines.extend(
                    [
                        "",
                        f"#### {relationship['id']} ({relationship['source']} -> {relationship['target']})",
                        f"- Quantitative call: {relationship['assay_cutoff_ordering_call']}",
                        f"- Basis: {ordering['basis']}",
                        "",
                        "| Chemical | DTXSID | CAS RN | Upstream cutoff | Downstream cutoff | Ordering |",
                        "| --- | --- | --- | ---: | ---: | --- |",
                    ]
                )
                for chemical in ordering["supporting_chemicals"]:
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                chemical.get("preferred_name") or "",
                                chemical.get("dtxsid") or "",
                                chemical.get("casrn") or "",
                                _format_optional_number(chemical.get("upstream_best_activity_cutoff")),
                                _format_optional_number(chemical.get("downstream_best_activity_cutoff")),
                                chemical.get("ordering") or "",
                            ]
                        )
                        + " |"
                    )
    else:
        lines.extend(["", "- No draft relationships were available for quantitative review."])

    lines.extend(["", "## Evidence Gaps"])
    if evidence_gaps is None:
        lines.append("- Evidence-gap review was not included for this artifact.")
    else:
        gap_summary = evidence_gaps["summary"]
        lines.extend(
            [
                "| Gap scope | Count |",
                "| --- | ---: |",
                f"| Total gaps | {gap_summary['total_gap_count']} |",
                f"| Blocking gaps | {gap_summary['blocking_gap_count']} |",
                f"| Advisory gaps | {gap_summary['advisory_gap_count']} |",
                f"| Global gaps | {gap_summary['global_gap_count']} |",
                f"| Key event gaps | {gap_summary['key_event_gap_count']} |",
                f"| Relationship gaps | {gap_summary['relationship_gap_count']} |",
                f"| Stressor gaps | {gap_summary['stressor_gap_count']} |",
                f"| KE assay-mapping gaps | {gap_summary['assay_mapping_gap_count']} |",
            ]
        )

        key_event_gap_rows = [item for item in evidence_gaps["key_events"] if item["gaps"]]
        if key_event_gap_rows:
            lines.extend(
                [
                    "",
                    "### Key Event Gap Hotspots",
                    "| Key event | Gap count | Missing items |",
                    "| --- | ---: | --- |",
                ]
            )
            for item in key_event_gap_rows:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"{item['id']} ({item['title'] or 'Untitled'})",
                            str(item["gap_count"]),
                            "; ".join(gap["title"] for gap in item["gaps"]),
                        ]
                    )
                    + " |"
                )

        relationship_gap_rows = [item for item in evidence_gaps["relationships"] if item["gaps"]]
        if relationship_gap_rows:
            lines.extend(
                [
                    "",
                    "### Relationship Gap Hotspots",
                    "| Relationship | Gap count | Missing items |",
                    "| --- | ---: | --- |",
                ]
            )
            for item in relationship_gap_rows:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"{item['id']} ({item['source']} -> {item['target']})",
                            str(item["gap_count"]),
                            "; ".join(gap["title"] for gap in item["gaps"]),
                        ]
                    )
                    + " |"
                )

        stressor_gap_rows = [item for item in evidence_gaps["stressors"] if item["gaps"]]
        if stressor_gap_rows:
            lines.extend(
                [
                    "",
                    "### Stressor Gap Hotspots",
                    "| Stressor | Gap count | Missing items |",
                    "| --- | ---: | --- |",
                ]
            )
            for item in stressor_gap_rows:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            item["label"] or item["stressor_id"] or "Unknown stressor",
                            str(item["gap_count"]),
                            "; ".join(gap["title"] for gap in item["gaps"]),
                        ]
                    )
                    + " |"
                )

    lines.extend(["", "## Chemical Activity Overlay"])
    if chemical_trace is None:
        lines.append("- No chemical activity overlay was requested for this artifact.")
    else:
        chemical = chemical_trace["chemical"]
        summary = chemical_trace["summary"]
        lines.extend(
            [
                f"- Chemical: {chemical.get('preferred_name') or chemical.get('dtxsid') or 'Unknown'}",
                f"- DTXSID: {chemical.get('dtxsid') or 'Not resolved'}",
                f"- Active key events: {summary['active_key_event_count']}",
                f"- Inactive key events: {summary['inactive_key_event_count']}",
                f"- No matching bioactivity: {summary['no_matching_bioactivity_key_event_count']}",
                f"- Unmapped key events: {summary['unmapped_key_event_count']}",
                "",
                "| Key event | Role | Activity state | Max hitcall | Best cutoff | Matching assays |",
                "| --- | --- | --- | ---: | ---: | ---: |",
            ]
        )
        for key_event in chemical_trace["key_events"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{key_event['id']} ({key_event['title'] or 'Untitled'})",
                        key_event.get("event_role") or "",
                        key_event["activity_state"],
                        _format_optional_number(key_event["max_hitcall"]),
                        _format_optional_number(key_event["best_activity_cutoff"]),
                        str(key_event["matching_assay_count"]),
                    ]
                )
                + " |"
            )

    _append_external_support_section(lines, bundle.get("external_support"))

    lines.extend(["", "## Recommended Next Actions"])
    for recommendation in recommendations:
        lines.append(f"- {recommendation}")

    lines.extend(
        [
            "",
            "## Limitations and Interpretation",
            "- These results combine draft-graph validation with assay-derived heuristics and should not be treated as a definitive causal proof.",
            "- Quantitative ordering signals are supplemental review evidence, not a curated qAOP model.",
            "- Chemical activity overlays highlight assay-supported draft nodes for one chemical and do not prove full-pathway traversal.",
        ]
    )
    for limitation in bundle["limitations"]:
        lines.append(f"- {limitation}")

    return "\n".join(lines) + "\n"


def _append_external_support_section(
    lines: list[str],
    external_support: dict[str, Any] | None,
) -> None:
    lines.extend(["", "## External Support"])
    if external_support is None:
        lines.append("- No external Registry support bundles are attached to this draft.")
        return

    summary = external_support.get("summary", {})
    imports = external_support.get("imports", [])
    attached_bundle_count = int(summary.get("attached_bundle_count", 0) or 0)
    if attached_bundle_count == 0:
        lines.append("- No external Registry support bundles are attached to this draft.")
        return

    lines.extend(
        [
            f"- Attached Registry bundles: {attached_bundle_count}",
            f"- Review-ready imported bundles: {summary.get('ready_bundle_count', 0)}",
            f"- Imported evidence items: {summary.get('total_evidence_item_count', 0)}",
            f"- Bounded-use warnings: {summary.get('total_bounded_use_warning_count', 0)}",
            f"- Scientific-review flags: {summary.get('total_scientific_review_flag_count', 0)}",
            f"- Blocking imported-support issues: {summary.get('blocking_issue_count', 0)}",
            f"- Advisory imported-support issues: {summary.get('advisory_issue_count', 0)}",
        ]
    )

    for imported_bundle in imports:
        source = imported_bundle.get("source", {})
        imported_summary = imported_bundle.get("summary", {})
        bundle_id = source.get("bundle_id") or "unknown bundle"
        import_plan = imported_bundle.get("draft_import_plan", {})
        lines.extend(
            [
                "",
                f"### Bundle `{bundle_id}`",
                f"- Source version: {source.get('source_version') or 'Not reported'}",
                f"- Created at: {source.get('created_at') or 'Not reported'}",
                f"- Ready for AOP review: {_yes_no(bool(imported_summary.get('ready_for_aop_review')))}",
                f"- Evidence items: {imported_summary.get('evidence_item_count', 0)}",
                f"- Direct applicability assessments: {imported_summary.get('direct_applicability_count', 0)}",
                f"- Partial applicability assessments: {imported_summary.get('partial_applicability_count', 0)}",
                f"- Indirect applicability assessments: {imported_summary.get('indirect_applicability_count', 0)}",
                f"- Non-comparable applicability assessments: {imported_summary.get('not_comparable_applicability_count', 0)}",
                f"- Suggested references: {len(import_plan.get('suggested_references', []))}",
                f"- Attachable Registry artifact refs: {len(import_plan.get('attachable_registry_artifact_refs', []))}",
            ]
        )
        for warning in imported_bundle.get("bounded_use_warnings", []):
            lines.append(f"- Warning: {warning}")
        for flag in imported_bundle.get("scientific_review_flags", []):
            lines.append(f"- Scientific-review flag: {flag}")
        for mapping_note in import_plan.get("required_manual_mapping", []):
            lines.append(f"- Manual mapping: {mapping_note}")


def _build_draft_review_recommendations(bundle: dict[str, Any]) -> list[str]:
    bundle_summary = bundle["bundle_summary"]
    quantitative_summary = bundle["quantitative_review"]["summary"]
    failing_ids = {
        item["id"]
        for item in bundle["validation"]["results"]
        if item["status"] == "fail"
    }
    recommendations: list[str] = []

    if bundle_summary["validator_error_count"] > 0:
        recommendations.append("Resolve blocking validation findings before external scientific review.")
    elif bundle_summary["validator_warning_count"] > 0:
        recommendations.append("Address non-blocking validation warnings to strengthen the scientific handoff package.")

    if {"ke_event_role_coverage", "topology_anchor_inference_used"} & failing_ids:
        recommendations.append(
            "Assign explicit `event_role` values to all draft key events so topology review anchors on authored intent rather than inference."
        )

    if "topology_directional_concordance_assessable" in failing_ids:
        recommendations.append(
            "Add explicit KE and KER polarity metadata so directional concordance can be assessed deterministically."
        )

    if "ker_assay_cutoff_ordering_assessable" in failing_ids or (
        quantitative_summary["linked_stressor_count"] > 0
        and quantitative_summary["assessable_relationship_count"] == 0
    ):
        recommendations.append(
            "Link draft stressors with resolvable identifiers and keep assay-mappable KE descriptions so quantitative ordering can be evaluated."
        )

    if bundle_summary["assay_cutoff_discordant_relationship_count"] > 0:
        recommendations.append(
            "Review discordant KER assay-cutoff ordering results and decide whether the pathway logic, stressor mapping, or assay evidence needs revision."
        )

    if not bundle_summary["chemical_trace_included"]:
        recommendations.append(
            "Provide one representative chemical identifier when you want a draft activity overlay for expert review."
        )
    elif bundle_summary["chemical_trace_included"] and bundle_summary["active_key_event_count"] == 0:
        recommendations.append(
            "The requested chemical overlay did not activate mapped key events; verify the chemical identity, hitcall threshold, and assay coverage."
        )

    if not recommendations:
        recommendations.append(
            "No immediate blocking actions were identified; the draft package is ready for scientific review with the listed caveats."
        )

    return list(dict.fromkeys(recommendations))


def _draft_evidence_gap(
    *,
    gap_id: str,
    severity: Literal["error", "warning"],
    category: str,
    title: str,
    detail: str,
    source: str,
    related_check_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": gap_id,
        "severity": severity,
        "category": category,
        "title": title,
        "detail": detail,
        "source": source,
        "related_check_ids": list(related_check_ids or []),
    }


def _draft_validation_gap_category(check_id: str) -> str:
    if check_id.startswith("topology_"):
        return "topology"
    if check_id.startswith("ker_assay_cutoff"):
        return "quantitative"
    if check_id == "stressor_links":
        return "stressor"
    return "metadata"


def _build_draft_global_evidence_gaps(
    validation_failures: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    global_check_ids = [
        "aop_root",
        "title_present",
        "title_format",
        "description_present",
        "adverse_outcome_present",
        "applicability_present",
        "references_present",
        "graphical_representation_present",
        "contact_present",
        "key_event_count",
        "ker_count",
        "stressor_links",
        "topology_anchor_inference_used",
        "topology_mie_present",
        "topology_ao_present",
        "topology_cycle_free",
        "topology_mie_to_ao_path_exists",
        "topology_anchor_degree_consistency",
        "topology_unanchored_key_events",
        "topology_directional_concordance_assessable",
        "topology_directional_concordance",
        "ker_assay_cutoff_ordering_assessable",
        "ker_assay_cutoff_ordering",
    ]
    gaps: list[dict[str, Any]] = []
    for check_id in global_check_ids:
        failure = validation_failures.get(check_id)
        if failure is None:
            continue
        gaps.append(
            _draft_evidence_gap(
                gap_id=check_id,
                severity=failure["severity"],
                category=_draft_validation_gap_category(check_id),
                title=failure["label"],
                detail=failure["message"],
                source="validation",
                related_check_ids=[check_id],
            )
        )
    return gaps


def _build_draft_key_event_evidence_gap_rows(
    *,
    key_events: list[Any],
    assay_search_reports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    measurement_keys = {"measurement", "measurement_methods", "how_it_is_measured", "methods"}
    applicability_keys = {
        "applicability",
        "species",
        "sex",
        "life_stage",
        "taxonomic_applicability",
        "taxa",
    }
    rows: list[dict[str, Any]] = []
    assay_mapping_gap_count = 0

    for entity, report in zip(key_events, assay_search_reports, strict=False):
        attributes = dict(entity.attributes)
        assay_results = list(report.get("results") or [])
        assay_limitations = list(report.get("limitations") or [])
        gaps: list[dict[str, Any]] = []

        if attributes.get("event_role") not in {"mie", "intermediate", "ao"}:
            gaps.append(
                _draft_evidence_gap(
                    gap_id="missing_event_role",
                    severity="warning",
                    category="topology",
                    title="Key event is missing an explicit topology role",
                    detail="Assign `event_role` as `mie`, `intermediate`, or `ao` so topology review anchors on authored intent instead of graph inference.",
                    source="draft_record",
                    related_check_ids=["ke_event_role_coverage", "topology_anchor_inference_used"],
                )
            )
        if not any(attributes.get(key) for key in measurement_keys):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="missing_measurement_guidance",
                    severity="warning",
                    category="measurement",
                    title="Key event is missing measurement guidance",
                    detail="Add measurement or detection guidance so reviewers know how this key event would be observed.",
                    source="draft_record",
                    related_check_ids=["ke_measurement_coverage"],
                )
            )
        if not any(attributes.get(key) for key in applicability_keys):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="missing_applicability_metadata",
                    severity="warning",
                    category="applicability",
                    title="Key event is missing applicability metadata",
                    detail="Add species, life stage, sex, or broader applicability metadata for this key event.",
                    source="draft_record",
                    related_check_ids=["ke_applicability_coverage"],
                )
            )
        essentiality = attributes.get("essentiality")
        if essentiality is None:
            gaps.append(
                _draft_evidence_gap(
                    gap_id="missing_essentiality",
                    severity="warning",
                    category="essentiality",
                    title="Key event is missing explicit essentiality metadata",
                    detail="Provide a governed essentiality object even when the current call is `not_assessed` or `not_reported`.",
                    source="draft_record",
                    related_check_ids=["ke_essentiality_coverage"],
                )
            )
        elif not is_governed_ke_essentiality(essentiality):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="invalid_essentiality",
                    severity="error",
                    category="essentiality",
                    title="Key event essentiality does not follow the governed draft schema",
                    detail="Use the object form `{evidence_call, rationale, references?, provenance?}` for key-event essentiality metadata.",
                    source="draft_record",
                    related_check_ids=["ke_essentiality_shape"],
                )
            )

        if not assay_results:
            assay_mapping_gap_count += 1
            unavailable_detail = next(
                (
                    item
                    for item in assay_limitations
                    if "unavailable" in item.lower()
                    or "unauthorized" in item.lower()
                    or "not configured" in item.lower()
                ),
                None,
            )
            if unavailable_detail is not None:
                gaps.append(
                    _draft_evidence_gap(
                        gap_id="assay_search_unavailable",
                        severity="warning",
                        category="assay_mapping",
                        title="Assay search was unavailable for this key event",
                        detail=unavailable_detail,
                        source="assay_search",
                    )
                )
            else:
                gaps.append(
                    _draft_evidence_gap(
                        gap_id="no_assay_candidates",
                        severity="warning",
                        category="assay_mapping",
                        title="No candidate assays were found for this key event",
                        detail=(
                            assay_limitations[-1]
                            if assay_limitations
                            else "No CompTox assay candidates matched the derived key-event terms."
                        ),
                        source="assay_search",
                    )
                )
        elif any(
            "did not expose gene-like symbols" in item.lower()
            for item in assay_limitations
        ):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="broad_phrase_only_assay_mapping",
                    severity="warning",
                    category="assay_mapping",
                    title="Assay mapping relies on broad phrase matching",
                    detail=next(
                        item
                        for item in assay_limitations
                        if "did not expose gene-like symbols" in item.lower()
                    ),
                    source="assay_search",
                )
            )

        top_assay = assay_results[0] if assay_results else None
        rows.append(
            {
                "id": entity.identifier,
                "title": attributes.get("title"),
                "event_type": attributes.get("event_type"),
                "event_role": attributes.get("event_role"),
                "assay_candidate_count": len(assay_results),
                "top_assay_name": top_assay.get("assay_name") if top_assay else None,
                "top_assay_specificity_score": top_assay.get("specificity_score") if top_assay else None,
                "assay_search_limitations": assay_limitations,
                "gap_count": len(gaps),
                "gaps": gaps,
            }
        )

    return rows, assay_mapping_gap_count


def _build_draft_relationship_evidence_gap_rows(
    *,
    kers: list[Any],
    quantitative_relationships_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    empirical_support_keys = {
        "empirical_support",
        "evidence",
        "evidence_supporting_this_ker",
    }
    quantitative_support_keys = {
        "quantitative_understanding",
        "response_response_relationship",
    }

    for rel in kers:
        attributes = dict(rel.attributes)
        quantitative_record = quantitative_relationships_by_id.get(rel.identifier, {})
        assay_cutoff_ordering = quantitative_record.get("assay_cutoff_ordering") or {}
        gaps: list[dict[str, Any]] = []

        if not (
            attributes.get("plausibility")
            or attributes.get("biological_plausibility")
            or rel.attributes.get("plausibility")
        ):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="missing_plausibility",
                    severity="warning",
                    category="evidence",
                    title="KER is missing biological plausibility text",
                    detail="Add a biological plausibility rationale explaining why the upstream event drives the downstream event.",
                    source="draft_record",
                    related_check_ids=["ker_plausibility_coverage"],
                )
            )
        if not any(attributes.get(key) for key in empirical_support_keys):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="missing_empirical_support",
                    severity="warning",
                    category="evidence",
                    title="KER is missing empirical support evidence",
                    detail="Add empirical evidence or observations supporting this key event relationship.",
                    source="draft_record",
                    related_check_ids=["ker_empirical_support_coverage"],
                )
            )
        if not any(attributes.get(key) for key in quantitative_support_keys):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="missing_quantitative_understanding",
                    severity="warning",
                    category="quantitative",
                    title="KER is missing quantitative understanding",
                    detail="Add response-response or other quantitative understanding details for this relationship where known.",
                    source="draft_record",
                    related_check_ids=["ker_quantitative_support_coverage"],
                )
            )
        if quantitative_record.get("assay_cutoff_ordering_call") == "not_reported":
            gaps.append(
                _draft_evidence_gap(
                    gap_id="assay_cutoff_not_assessable",
                    severity="warning",
                    category="quantitative",
                    title="Assay cutoff ordering is not assessable for this KER",
                    detail=assay_cutoff_ordering.get("basis")
                    or "This relationship did not expose enough linked-stressor assay evidence for quantitative cutoff ordering review.",
                    source="quantitative_review",
                    related_check_ids=["ker_assay_cutoff_ordering_assessable"],
                )
            )
        elif assay_cutoff_ordering.get("discordant_chemical_count", 0) > 0:
            gaps.append(
                _draft_evidence_gap(
                    gap_id="assay_cutoff_ordering_discordant",
                    severity="warning",
                    category="quantitative",
                    title="Assay cutoff ordering conflicts with the drafted KER direction",
                    detail=assay_cutoff_ordering.get("basis")
                    or "One or more supporting chemicals showed discordant upstream/downstream assay cutoff ordering.",
                    source="quantitative_review",
                    related_check_ids=["ker_assay_cutoff_ordering"],
                )
            )

        rows.append(
            {
                "id": rel.identifier,
                "source": rel.source,
                "target": rel.target,
                "type": rel.type,
                "plausibility": rel.attributes.get("plausibility"),
                "status": rel.attributes.get("status"),
                "assay_cutoff_ordering_call": quantitative_record.get(
                    "assay_cutoff_ordering_call",
                    "not_reported",
                ),
                "assay_cutoff_supporting_chemical_count": quantitative_record.get(
                    "assay_cutoff_supporting_chemical_count",
                    0,
                ),
                "gap_count": len(gaps),
                "gaps": gaps,
            }
        )

    return rows


def _build_draft_stressor_evidence_gap_rows(
    *,
    stressors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stressor in stressors:
        gaps: list[dict[str, Any]] = []
        if not stressor.get("searchable"):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="unsearchable_stressor",
                    severity="warning",
                    category="stressor",
                    title="Stressor cannot be resolved for downstream evidence review",
                    detail="Add a stable stressor name, CAS RN, or DTXSID so quantitative and mapping review can resolve this stressor.",
                    source="draft_record",
                    related_check_ids=["stressor_links", "ker_assay_cutoff_ordering_assessable"],
                )
            )
        elif not (stressor.get("dtxsid") or stressor.get("casrn")):
            gaps.append(
                _draft_evidence_gap(
                    gap_id="missing_structured_identifier",
                    severity="warning",
                    category="stressor",
                    title="Stressor lacks a structured identifier",
                    detail="This stressor is only searchable by free text. Add a CAS RN or DTXSID for more reliable assay and quantitative evidence resolution.",
                    source="draft_record",
                    related_check_ids=["ker_assay_cutoff_ordering_assessable"],
                )
            )
        rows.append(
            {
                "stressor_id": stressor.get("stressor_id"),
                "label": stressor.get("label"),
                "source": stressor.get("source"),
                "casrn": stressor.get("casrn"),
                "dtxsid": stressor.get("dtxsid"),
                "linked_target_ids": list(stressor.get("linked_target_ids") or []),
                "searchable": bool(stressor.get("searchable")),
                "gap_count": len(gaps),
                "gaps": gaps,
            }
        )
    return rows


def _build_draft_evidence_gap_recommendations(
    *,
    global_gaps: list[dict[str, Any]],
    key_event_rows: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
    stressor_rows: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    global_gap_ids = {gap["id"] for gap in global_gaps}
    key_event_gap_ids = {gap["id"] for item in key_event_rows for gap in item["gaps"]}
    relationship_gap_ids = {gap["id"] for item in relationship_rows for gap in item["gaps"]}
    stressor_gap_ids = {gap["id"] for item in stressor_rows for gap in item["gaps"]}
    has_errors = any(gap["severity"] == "error" for gap in global_gaps) or any(
        gap["severity"] == "error"
        for item in key_event_rows + relationship_rows + stressor_rows
        for gap in item["gaps"]
    )

    if has_errors:
        recommendations.append("Resolve blocking draft-contract or topology gaps before external scientific review.")

    if (
        global_gap_ids
        & {
            "topology_anchor_inference_used",
            "topology_mie_present",
            "topology_ao_present",
            "topology_cycle_free",
            "topology_mie_to_ao_path_exists",
            "topology_unanchored_key_events",
        }
        or "missing_event_role" in key_event_gap_ids
    ):
        recommendations.append(
            "Complete the draft topology first: assign explicit `event_role` values and repair any missing or inconsistent MIE-to-AO paths."
        )

    if key_event_gap_ids & {
        "missing_measurement_guidance",
        "missing_applicability_metadata",
        "missing_essentiality",
        "invalid_essentiality",
    }:
        recommendations.append(
            "Bring every key event up to the governed review baseline with measurement guidance, applicability metadata, and explicit essentiality status."
        )

    if key_event_gap_ids & {
        "assay_search_unavailable",
        "no_assay_candidates",
        "broad_phrase_only_assay_mapping",
    }:
        recommendations.append(
            "Tighten KE assay routing by enriching key-event titles, structured gene identifiers, and measurement metadata so assay mapping is more specific and complete."
        )

    if relationship_gap_ids & {
        "missing_plausibility",
        "missing_empirical_support",
        "missing_quantitative_understanding",
    }:
        recommendations.append(
            "Fill the missing KER evidence fields explicitly: biological plausibility, empirical support, and quantitative understanding."
        )

    if stressor_gap_ids & {"unsearchable_stressor", "missing_structured_identifier"} or relationship_gap_ids & {
        "assay_cutoff_not_assessable",
    }:
        recommendations.append(
            "Normalize linked stressors to CAS RN or DTXSID where possible so quantitative ordering review can resolve chemicals deterministically."
        )

    if "assay_cutoff_ordering_discordant" in relationship_gap_ids:
        recommendations.append(
            "Investigate discordant assay cutoff ordering before publication; the current KER direction, stressor mapping, or assay evidence may need revision."
        )

    if global_gap_ids & {
        "topology_directional_concordance_assessable",
        "topology_directional_concordance",
    }:
        recommendations.append(
            "Add explicit KE directionality and KER effect metadata so directional concordance can be reviewed deterministically."
        )

    if not recommendations:
        recommendations.append(
            "No immediate evidence gaps were identified beyond the standard review caveats already reported in the draft bundle."
        )

    return list(dict.fromkeys(recommendations))


def _draft_review_artifact_section_titles(
    artifact_profile: Literal["review", "publication"],
) -> list[str]:
    if artifact_profile == "publication":
        return [
            "Executive Summary",
            "Draft Context",
            "Review Findings",
            "Quantitative Evidence",
            "Evidence Gaps",
            "Chemical Activity Overlay",
            "External Support",
            "Recommended Next Actions",
            "Limitations and Interpretation",
        ]

    return [
        "Draft Review Summary",
        "Validation Findings",
        "Quantitative Review",
        "Chemical Trace",
        "Evidence Gaps",
        "External Support",
        "Recommended Next Actions",
        "Limitations",
    ]


def _format_optional_number(value: Any) -> str:
    if value is None:
        return "Not reported"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _infer_artifact_profile_from_path(artifact_path: Path) -> str:
    stem = artifact_path.stem.lower()
    return "publication" if stem.endswith("_publication") else "review"


def _infer_artifact_format_from_path(artifact_path: Path) -> str:
    return "markdown" if artifact_path.suffix.lower() == ".md" else "json"


def _metadata_payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=repr,
        ).encode("utf-8")
    ).hexdigest()


def _build_draft_version_integrity(version: Any) -> dict[str, str]:
    metadata = version.metadata
    provenance_checksum = getattr(
        metadata,
        "provenance_checksum",
        "",
    ) or compute_provenance_checksum(metadata.provenance)
    return {
        "checksum_algorithm": metadata.checksum_algorithm,
        "graph_sha256": metadata.checksum,
        "previous_graph_sha256": metadata.previous_checksum,
        "provenance_checksum_algorithm": getattr(
            metadata,
            "provenance_checksum_algorithm",
            "sha256-v1",
        ),
        "provenance_sha256": provenance_checksum,
    }


def _serialize_graph_entity(entity: Any) -> dict[str, Any]:
    return {
        "identifier": entity.identifier,
        "type": entity.type,
        "attributes": dict(entity.attributes),
    }


def _serialize_graph_relationship(relationship: Any) -> dict[str, Any]:
    return {
        "identifier": relationship.identifier,
        "source": relationship.source,
        "target": relationship.target,
        "type": relationship.type,
        "attributes": dict(relationship.attributes),
    }


def _serialize_signature(signature: Any) -> dict[str, Any]:
    return {
        "signer_user_id": signature.signer_user_id,
        "signature_meaning": signature.signature_meaning,
        "timestamp_utc": signature.timestamp_utc,
        "content_hash": signature.content_hash,
        "signature_value": signature.signature_value,
        "cert_chain": list(signature.cert_chain),
    }


def _build_draft_snapshot_record(draft: Any, version: Any) -> dict[str, Any]:
    entities = [
        _serialize_graph_entity(entity)
        for entity in sorted(
            version.graph.entities.values(),
            key=lambda item: item.identifier,
        )
    ]
    relationships = [
        _serialize_graph_relationship(relationship)
        for relationship in sorted(
            version.graph.relationships.values(),
            key=lambda item: item.identifier,
        )
    ]
    metadata = version.metadata
    return {
        "draft": {
            "draft_id": draft.draft_id,
            "title": draft.title,
            "status": draft.status,
            "created_at": _isoformat_utc(draft.created_at),
            "updated_at": _isoformat_utc(draft.updated_at),
            "tags": list(draft.tags),
            "version_count": len(draft.versions),
        },
        "version": {
            "version_id": version.version_id,
            "author": metadata.author,
            "summary": metadata.summary,
            "created_at": _isoformat_utc(metadata.created_at),
            "provenance": dict(metadata.provenance),
            "checksum": metadata.checksum,
            "previous_checksum": metadata.previous_checksum,
            "checksum_algorithm": metadata.checksum_algorithm,
            "provenance_checksum": metadata.provenance_checksum,
            "provenance_checksum_algorithm": metadata.provenance_checksum_algorithm,
            "signatures": [
                _serialize_signature(signature)
                for signature in metadata.signatures
            ],
        },
        "graph": {
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "entities": entities,
            "relationships": relationships,
        },
        "diff_summary": {
            "added_entity_count": len(version.diff.added_entities),
            "removed_entity_count": len(version.diff.removed_entities),
            "updated_entity_count": len(version.diff.updated_entities),
            "added_relationship_count": len(version.diff.added_relationships),
            "removed_relationship_count": len(version.diff.removed_relationships),
            "updated_relationship_count": len(version.diff.updated_relationships),
        },
    }


def _recent_tool_call_audit_records(limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    return [
        record.to_dict()
        for record in tool_call_audit_log.list_records()[-limit:]
    ]


def _is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _normalize_artifact_integrity(
    metadata: dict[str, Any],
    *,
    actual_content_sha256: str,
) -> dict[str, Any]:
    raw_integrity = metadata.get("artifact_integrity")
    integrity = raw_integrity if isinstance(raw_integrity, dict) else {}
    content_sha256 = integrity.get("content_sha256") or metadata.get("sha256")
    metadata_sha256 = integrity.get("metadata_sha256")
    return {
        "algorithm": "sha256-v1",
        "content_sha256": content_sha256 if _is_sha256_hex(content_sha256) else actual_content_sha256,
        "metadata_sha256": metadata_sha256 if _is_sha256_hex(metadata_sha256) else None,
    }


def _build_artifact_integrity_check(
    *,
    actual_content_sha256: str,
    metadata: dict[str, Any] | None,
    metadata_error: str | None = None,
) -> dict[str, Any]:
    content_status = "not_verifiable"
    metadata_status = "not_verifiable"
    expected_content_sha256: str | None = None
    expected_metadata_sha256: str | None = None
    actual_metadata_sha256: str | None = None
    messages: list[str] = []

    if metadata_error is not None:
        metadata_status = "failed"
        messages.append(metadata_error)
    elif metadata is None:
        messages.append(
            "Metadata sidecar is unavailable, so stored artifact checksums could not be verified."
        )
    else:
        raw_integrity = metadata.get("artifact_integrity")
        integrity = raw_integrity if isinstance(raw_integrity, dict) else {}
        algorithm = integrity.get("algorithm")
        if raw_integrity is not None and algorithm != "sha256-v1":
            content_status = "failed"
            metadata_status = "failed"
            messages.append(
                f"Unsupported artifact integrity algorithm: {algorithm or 'not reported'}."
            )

        expected_content_sha256 = integrity.get("content_sha256") or metadata.get("sha256")
        if content_status != "failed":
            if expected_content_sha256 is None:
                messages.append("No stored content checksum was available for verification.")
            elif not _is_sha256_hex(expected_content_sha256):
                content_status = "failed"
                messages.append("Stored content checksum is not a valid SHA-256 hex digest.")
            elif expected_content_sha256 == actual_content_sha256:
                content_status = "verified"
            else:
                content_status = "failed"
                messages.append("Artifact content checksum does not match the metadata sidecar.")

        expected_metadata_sha256 = integrity.get("metadata_sha256")
        if metadata_status != "failed":
            if expected_metadata_sha256 is None:
                messages.append("No stored metadata checksum was available for verification.")
            elif not _is_sha256_hex(expected_metadata_sha256):
                metadata_status = "failed"
                messages.append("Stored metadata checksum is not a valid SHA-256 hex digest.")
            else:
                metadata_without_integrity = dict(metadata)
                metadata_without_integrity.pop("artifact_integrity", None)
                actual_metadata_sha256 = _metadata_payload_sha256(metadata_without_integrity)
                if expected_metadata_sha256 == actual_metadata_sha256:
                    metadata_status = "verified"
                else:
                    metadata_status = "failed"
                    messages.append("Metadata sidecar checksum does not match its integrity record.")

    if "failed" in {content_status, metadata_status}:
        overall_status = "failed"
    elif content_status == "verified" and metadata_status == "verified":
        overall_status = "verified"
    else:
        overall_status = "not_verifiable"

    return {
        "overall_status": overall_status,
        "content_status": content_status,
        "metadata_status": metadata_status,
        "content_sha256_actual": actual_content_sha256,
        "content_sha256_expected": expected_content_sha256,
        "metadata_sha256_actual": actual_metadata_sha256,
        "metadata_sha256_expected": expected_metadata_sha256,
        "messages": messages,
    }


def _build_saved_draft_review_artifact_index_item(
    artifact_path: Path,
    *,
    artifact_root_dir: Path,
) -> dict[str, Any]:
    resolved_path = artifact_path.resolve()
    metadata_path = _artifact_metadata_path(artifact_path)
    file_bytes = artifact_path.read_bytes()
    stat = artifact_path.stat()
    content_sha256 = hashlib.sha256(file_bytes).hexdigest()
    item = {
        "filename": artifact_path.name,
        "path": str(resolved_path),
        "relative_path": str(resolved_path.relative_to(artifact_root_dir)),
        "output_directory": str(artifact_path.parent.resolve()),
        "format": _infer_artifact_format_from_path(artifact_path),
        "artifact_profile": _infer_artifact_profile_from_path(artifact_path),
        "draft_id": None,
        "version_id": None,
        "bytes_written": stat.st_size,
        "sha256": content_sha256,
        "saved_at": _isoformat_utc(stat.st_mtime),
        "metadata_available": False,
        "metadata_path": str(metadata_path) if metadata_path.exists() else None,
        "bundle_summary": None,
        "evidence_gap_summary": None,
        "artifact_integrity": {
            "algorithm": "sha256-v1",
            "content_sha256": content_sha256,
            "metadata_sha256": None,
        },
        "draft_version_integrity": None,
        "integrity_check": _build_artifact_integrity_check(
            actual_content_sha256=content_sha256,
            metadata=None,
        ),
    }

    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except OSError as exc:
            item["integrity_check"] = _build_artifact_integrity_check(
                actual_content_sha256=content_sha256,
                metadata=None,
                metadata_error=f"Metadata sidecar could not be read: {exc}",
            )
            return item
        except json.JSONDecodeError as exc:
            item["integrity_check"] = _build_artifact_integrity_check(
                actual_content_sha256=content_sha256,
                metadata=None,
                metadata_error=f"Metadata sidecar could not be parsed as JSON: {exc.msg}",
            )
            return item

        item.update(
            {
                "format": metadata.get("format", item["format"]),
                "artifact_profile": metadata.get("artifact_profile", item["artifact_profile"]),
                "draft_id": metadata.get("draft_id"),
                "version_id": metadata.get("version_id"),
                "relative_path": metadata.get("relative_path", item["relative_path"]),
                "bytes_written": metadata.get("bytes_written", item["bytes_written"]),
                "saved_at": metadata.get("saved_at", item["saved_at"]),
                "metadata_available": True,
                "metadata_path": str(metadata_path),
                "bundle_summary": metadata.get("bundle_summary"),
                "evidence_gap_summary": metadata.get("evidence_gap_summary"),
                "artifact_integrity": _normalize_artifact_integrity(
                    metadata,
                    actual_content_sha256=content_sha256,
                ),
                "draft_version_integrity": metadata.get("draft_version_integrity"),
                "integrity_check": _build_artifact_integrity_check(
                    actual_content_sha256=content_sha256,
                    metadata=metadata,
                ),
            }
        )

    return item


def _normalize_artifact_relative_file_path(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("artifact_relative_path must not be empty")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(
            "artifact_relative_path must be a relative file path without empty, '.' or '..' segments"
        )
    return "/".join(parts)


def _resolve_saved_artifact_path(
    *,
    artifact_path: str | None,
    artifact_relative_path: str | None,
) -> Path:
    artifact_root_dir = _resolve_artifact_output_directory()
    if artifact_relative_path:
        return (artifact_root_dir / artifact_relative_path).resolve()
    if artifact_path is None:
        raise ValueError("Provide artifact_path or artifact_relative_path")
    resolved = Path(artifact_path).expanduser().resolve()
    if artifact_root_dir not in resolved.parents and resolved != artifact_root_dir:
        raise ValueError("artifact_path must resolve under the configured draft review artifact directory")
    return resolved


def _extract_draft_review_artifact_title(
    content: str,
    *,
    format_name: Literal["markdown", "json"],
    fallback_title: str,
) -> str:
    if format_name == "markdown":
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip() or fallback_title
        return fallback_title

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return fallback_title

    draft = payload.get("draft")
    if isinstance(draft, dict) and draft.get("title"):
        return str(draft["title"])
    bundle = payload.get("bundle")
    if isinstance(bundle, dict):
        draft = bundle.get("draft")
        if isinstance(draft, dict) and draft.get("title"):
            return str(draft["title"])
        if bundle.get("draft_id"):
            return f"Draft Review Artifact: {bundle['draft_id']}"
    if payload.get("draft_id"):
        return f"Draft Review Artifact: {payload['draft_id']}"
    return fallback_title


def _strip_leading_markdown_heading(content: str) -> str:
    lines = content.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    stripped = "\n".join(lines).strip()
    return stripped


def _build_linear_review_document_markdown(
    *,
    artifact_content: str,
    artifact_format: Literal["markdown", "json"],
    source_record: dict[str, Any],
    summary: dict[str, Any] | None,
    warnings: list[str],
) -> str:
    lines = [
        "## Handoff Context",
        f"- Source mode: {'Saved artifact' if source_record['mode'] == 'saved_artifact' else 'Live draft export'}",
        f"- Draft ID: {source_record.get('draft_id') or 'Not recorded'}",
        f"- Version ID: {source_record.get('version_id') or 'Not recorded'}",
        f"- Artifact profile: {source_record.get('artifact_profile') or 'Not recorded'}",
    ]
    if source_record.get("relative_path"):
        lines.append(f"- Saved artifact: `{source_record['relative_path']}`")
    elif source_record.get("path"):
        lines.append(f"- Source path: `{source_record['path']}`")
    if source_record.get("saved_at"):
        lines.append(f"- Saved at: {source_record['saved_at']}")

    if summary is not None:
        lines.extend(
            [
                "",
                "## Review Snapshot",
                f"- Ready for review: {_yes_no(summary['ready_for_review'])}",
                f"- Validator errors: {summary['validator_error_count']}",
                f"- Validator warnings: {summary['validator_warning_count']}",
                f"- Assessable quantitative KER reviews: {summary['assay_cutoff_assessable_relationship_count']}",
                f"- Discordant quantitative KER reviews: {summary['assay_cutoff_discordant_relationship_count']}",
            ]
        )

    if warnings:
        lines.extend(["", "## Handoff Warnings"])
        for warning in warnings:
            lines.append(f"- {warning}")

    if artifact_format == "markdown":
        stripped = _strip_leading_markdown_heading(artifact_content)
        if stripped:
            lines.extend(["", stripped])
    else:
        lines.extend(["", "## Raw Review Artifact Payload", "```json", artifact_content.strip(), "```"])

    return "\n".join(lines).strip() + "\n"


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


class TraceChemicalOnDraftInput(BaseModel):
    draft_id: str
    version_id: Optional[str] = None
    dtxsid: Optional[str] = None
    cas: Optional[str] = None
    inchikey: Optional[str] = None
    name: Optional[str] = None
    assay_limit: int = Field(default=10, ge=1, le=25)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def ensure_identifier(self) -> "TraceChemicalOnDraftInput":
        if not (self.dtxsid or self.cas or self.inchikey or self.name):
            raise ValueError("Provide at least one chemical identifier: dtxsid, cas, inchikey, or name")
        return self


async def trace_chemical_on_draft(params: TraceChemicalOnDraftInput) -> dict[str, Any]:
    draft_store = get_draft_store()
    draft = draft_store.get_draft(params.draft_id)
    if draft is None:
        raise KeyError(f"Draft '{params.draft_id}' not found")

    version = _select_draft_version(draft, params.version_id)
    entities = list(version.graph.entities.values())
    relationships = list(version.graph.relationships.values())
    aop_entity = next((entity for entity in entities if entity.type == "AdverseOutcomePathway"), None)
    key_events = [entity for entity in entities if entity.type == "KeyEvent"]
    kers = [rel for rel in relationships if rel.type == "KeyEventRelationship"]

    comptox = get_comptox_client()
    chemical, resolution_limitations = await _resolve_trace_chemical(params, comptox=comptox)
    bioactivity_limitations: list[str] = []
    try:
        bioactivity_rows = await asyncio.to_thread(comptox.bioactivity_data_by_dtxsid, chemical["dtxsid"])
    except CompToxError as exc:
        bioactivity_rows = []
        bioactivity_limitations.extend(
            [
                "CompTox bioactivity retrieval was unavailable, so draft nodes could not be highlighted from chemical activity data.",
                f"CompTox detail: {exc}",
            ]
        )
    bioactivity_by_aeid = _aggregate_trace_bioactivity(bioactivity_rows)

    db_adapter = get_aop_db_adapter()
    search_reports = await asyncio.gather(
        *(
            db_adapter.search_assays_for_key_event(
                _draft_key_event_search_record(entity),
                limit=params.assay_limit,
            )
            for entity in key_events
        )
    )

    traced_key_events: list[dict[str, Any]] = []
    for entity, search_report in zip(key_events, search_reports, strict=False):
        assay_rows: list[dict[str, Any]] = []
        matching_assay_count = 0
        active_assay_count = 0
        hitcalls: list[float] = []
        cutoffs: list[float] = []
        for candidate in search_report["results"]:
            activity = bioactivity_by_aeid.get(candidate.get("aeid"))
            if activity:
                matching_assay_count += 1
                hitcalls.append(activity["max_hitcall"])
                if activity["best_activity_cutoff"] is not None:
                    cutoffs.append(activity["best_activity_cutoff"])
                if activity["max_hitcall"] >= params.min_hitcall:
                    active_assay_count += 1
            assay_rows.append(
                {
                    "aeid": candidate.get("aeid"),
                    "assay_name": candidate.get("assay_name"),
                    "match_score": candidate.get("match_score"),
                    "rank_score": candidate.get("rank_score", candidate.get("match_score")),
                    "specificity_score": candidate.get("specificity_score"),
                    "source": candidate.get("source"),
                    "matched_terms": list(candidate.get("matched_terms") or []),
                    "match_basis": list(candidate.get("match_basis") or []),
                    "gene_symbols": list(candidate.get("gene_symbols") or []),
                    "hitcall": activity["max_hitcall"] if activity else None,
                    "activity_cutoff": activity["best_activity_cutoff"] if activity else None,
                    "active": bool(activity and activity["max_hitcall"] >= params.min_hitcall),
                }
            )

        if not search_report["results"]:
            activity_state = "no_assay_candidates"
        elif matching_assay_count == 0:
            activity_state = "no_matching_bioactivity"
        elif active_assay_count > 0:
            activity_state = "active"
        else:
            activity_state = "inactive"

        traced_key_events.append(
            {
                "id": entity.identifier,
                "title": entity.attributes.get("title"),
                "event_type": entity.attributes.get("event_type"),
                "event_role": entity.attributes.get("event_role"),
                "activity_state": activity_state,
                "active": activity_state == "active",
                "assay_candidate_count": len(search_report["results"]),
                "matching_assay_count": matching_assay_count,
                "active_assay_count": active_assay_count,
                "max_hitcall": max(hitcalls) if hitcalls else None,
                "best_activity_cutoff": min(cutoffs) if cutoffs else None,
                "derived_search_terms": search_report["derived_search_terms"],
                "top_assays": assay_rows,
                "limitations": list(search_report["limitations"]),
            }
        )

    payload = {
        "draft_id": draft.draft_id,
        "version_id": version.version_id,
        "draft": {
            "aop_entity_id": aop_entity.identifier if aop_entity else None,
            "title": aop_entity.attributes.get("title") if aop_entity else draft.title,
            "adverse_outcome": aop_entity.attributes.get("adverse_outcome") if aop_entity else None,
        },
        "chemical": {
            "query": {
                "dtxsid": params.dtxsid,
                "cas": params.cas,
                "inchikey": params.inchikey,
                "name": params.name,
            },
            "dtxsid": chemical.get("dtxsid"),
            "preferred_name": chemical.get("preferred_name"),
            "casrn": chemical.get("casrn"),
            "inchikey": chemical.get("inchikey"),
            "matched_by": chemical.get("matched_by"),
        },
        "summary": {
            "key_event_count": len(key_events),
            "relationship_count": len(kers),
            "traced_key_event_count": sum(
                1 for item in traced_key_events if item["assay_candidate_count"] > 0
            ),
            "active_key_event_count": sum(
                1 for item in traced_key_events if item["activity_state"] == "active"
            ),
            "inactive_key_event_count": sum(
                1 for item in traced_key_events if item["activity_state"] == "inactive"
            ),
            "no_matching_bioactivity_key_event_count": sum(
                1 for item in traced_key_events if item["activity_state"] == "no_matching_bioactivity"
            ),
            "unmapped_key_event_count": sum(
                1 for item in traced_key_events if item["activity_state"] == "no_assay_candidates"
            ),
            "chemical_bioactivity_assay_count": len(bioactivity_by_aeid),
        },
        "key_events": traced_key_events,
        "relationships": [
            {
                "id": rel.identifier,
                "source": rel.source,
                "target": rel.target,
                "type": rel.type,
                "plausibility": rel.attributes.get("plausibility"),
                "status": rel.attributes.get("status"),
            }
            for rel in kers
        ],
        "limitations": [
            *resolution_limitations,
            *bioactivity_limitations,
            *(
                ["Draft does not currently contain any key events to trace."]
                if not key_events
                else []
            ),
            *(
                [
                    "No CompTox bioactivity rows were available for the resolved chemical DTXSID, so draft nodes remain unhighlighted."
                ]
                if not bioactivity_by_aeid
                else []
            ),
        ],
    }
    validate_payload(payload, namespace="read", name="trace_chemical_on_draft.response.schema")
    return payload


class ReviewDraftAssayCutoffOrderingInput(BaseModel):
    draft_id: str
    version_id: Optional[str] = None
    assay_limit: int = Field(default=5, ge=1, le=25)
    stressor_limit: int = Field(default=10, ge=1, le=50)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def review_draft_assay_cutoff_ordering(
    params: ReviewDraftAssayCutoffOrderingInput,
) -> dict[str, Any]:
    draft_store = get_draft_store()
    draft = draft_store.get_draft(params.draft_id)
    if draft is None:
        raise KeyError(f"Draft '{params.draft_id}' not found")

    version = _select_draft_version(draft, params.version_id)
    entities = list(version.graph.entities.values())
    relationships = list(version.graph.relationships.values())
    aop_entity = next((entity for entity in entities if entity.type == "AdverseOutcomePathway"), None)
    key_events = [entity for entity in entities if entity.type == "KeyEvent"]
    kers = [rel for rel in relationships if rel.type == "KeyEventRelationship"]
    stressor_links = [rel for rel in relationships if rel.type == "StressorLink"]
    stressor_records = _extract_draft_stressor_records(
        entities=entities,
        stressor_links=stressor_links,
    )
    assay_cutoff_records = await _build_draft_assay_cutoff_ordering_records(
        entities=entities,
        key_events=key_events,
        kers=kers,
        stressor_links=stressor_links,
        assay_limit=params.assay_limit,
        stressor_limit=params.stressor_limit,
        min_hitcall=params.min_hitcall,
    )
    assay_cutoff_by_id = {
        str(record.get("id")): dict(record)
        for record in assay_cutoff_records
        if record.get("id")
    }

    relationship_rows: list[dict[str, Any]] = []
    for rel in kers:
        assay_cutoff_ordering = dict(
            assay_cutoff_by_id.get(rel.identifier)
            or _not_reported_assay_cutoff_ordering(
                "No assay-cutoff ordering record could be derived for this draft relationship.",
                transformation="phase4_assay_cutoff_ordering_missing_draft_relationship_record",
            )
        )
        assay_cutoff_ordering.pop("id", None)
        relationship_rows.append(
            {
                "id": rel.identifier,
                "source": rel.source,
                "target": rel.target,
                "type": rel.type,
                "plausibility": rel.attributes.get("plausibility"),
                "status": rel.attributes.get("status"),
                "assay_cutoff_ordering_call": assay_cutoff_ordering["heuristic_call"],
                "assay_cutoff_supporting_chemical_count": assay_cutoff_ordering.get(
                    "supporting_chemical_count",
                    0,
                ),
                "assay_cutoff_ordering": assay_cutoff_ordering,
            }
        )

    assessable_relationship_count = sum(
        1 for row in relationship_rows if row["assay_cutoff_ordering_call"] != "not_reported"
    )
    discordant_relationship_count = sum(
        1
        for row in relationship_rows
        if row["assay_cutoff_ordering"].get("discordant_chemical_count", 0) > 0
    )
    limitations: list[str] = []
    if not key_events:
        limitations.append("Draft does not currently contain any key events to review.")
    if not kers:
        limitations.append("Draft does not currently contain any key event relationships to review.")
    if not stressor_links:
        limitations.append("Draft does not currently contain any linked stressors for quantitative review.")
    if len(stressor_records) > params.stressor_limit:
        limitations.append(
            f"Only the first {params.stressor_limit} linked draft stressors were scanned for assay-cutoff ordering."
        )
    limitations.extend(
        row["assay_cutoff_ordering"]["basis"]
        for row in relationship_rows
        if row["assay_cutoff_ordering_call"] == "not_reported"
    )
    payload = {
        "draft_id": draft.draft_id,
        "version_id": version.version_id,
        "draft": {
            "aop_entity_id": aop_entity.identifier if aop_entity else None,
            "title": aop_entity.attributes.get("title") if aop_entity else draft.title,
            "adverse_outcome": aop_entity.attributes.get("adverse_outcome") if aop_entity else None,
        },
        "review_parameters": {
            "assay_limit": params.assay_limit,
            "stressor_limit": params.stressor_limit,
            "min_hitcall": params.min_hitcall,
        },
        "summary": {
            "key_event_count": len(key_events),
            "relationship_count": len(kers),
            "linked_stressor_count": len(stressor_records),
            "scanned_stressor_count": min(len(stressor_records), params.stressor_limit),
            "searchable_stressor_count": sum(
                1
                for record in stressor_records
                if record.get("dtxsid") or record.get("casrn") or record.get("label")
            ),
            "assessable_relationship_count": assessable_relationship_count,
            "concordant_relationship_count": assessable_relationship_count - discordant_relationship_count,
            "discordant_relationship_count": discordant_relationship_count,
            "not_reported_relationship_count": sum(
                1 for row in relationship_rows if row["assay_cutoff_ordering_call"] == "not_reported"
            ),
            "supporting_chemical_count": sum(
                row["assay_cutoff_ordering"].get("supporting_chemical_count", 0)
                for row in relationship_rows
            ),
        },
        "stressors": [
            {
                "stressor_id": record.get("stressor_id"),
                "label": record.get("label"),
                "source": record.get("source"),
                "casrn": record.get("casrn"),
                "dtxsid": record.get("dtxsid"),
                "linked_target_ids": list(record.get("linked_target_ids") or []),
                "searchable": bool(record.get("dtxsid") or record.get("casrn") or record.get("label")),
            }
            for record in stressor_records
        ],
        "key_events": [
            {
                "id": entity.identifier,
                "title": entity.attributes.get("title"),
                "event_type": entity.attributes.get("event_type"),
                "event_role": entity.attributes.get("event_role"),
            }
            for entity in key_events
        ],
        "relationships": relationship_rows,
        "limitations": list(dict.fromkeys(limitations)),
    }
    validate_payload(
        payload,
        namespace="read",
        name="review_draft_assay_cutoff_ordering.response.schema",
    )
    return payload


class ReviewDraftBundleInput(BaseModel):
    draft_id: str
    version_id: Optional[str] = None
    dtxsid: Optional[str] = None
    cas: Optional[str] = None
    inchikey: Optional[str] = None
    name: Optional[str] = None
    assay_limit: int = Field(default=5, ge=1, le=25)
    stressor_limit: int = Field(default=10, ge=1, le=50)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


class ReviewRegistryHandoffBundleInput(BaseModel):
    bundle: dict[str, Any]


async def review_registry_handoff_bundle(
    params: ReviewRegistryHandoffBundleInput,
) -> dict[str, Any]:
    payload = build_registry_handoff_review(params.bundle)
    validate_payload(
        payload,
        namespace="read",
        name="review_registry_handoff_bundle.response.schema",
    )
    return payload


async def review_draft_bundle(params: ReviewDraftBundleInput) -> dict[str, Any]:
    draft, version, entities, relationships = _load_draft_version_graph(
        params.draft_id,
        params.version_id,
    )
    validation, quantitative_review = await asyncio.gather(
        validate_draft_oecd(
            ValidateDraftOecdInput(
                draft_id=params.draft_id,
                version_id=params.version_id,
            )
        ),
        review_draft_assay_cutoff_ordering(
            ReviewDraftAssayCutoffOrderingInput(
                draft_id=params.draft_id,
                version_id=params.version_id,
                assay_limit=params.assay_limit,
                stressor_limit=params.stressor_limit,
                min_hitcall=params.min_hitcall,
            )
        ),
    )

    chemical_query = {
        "dtxsid": params.dtxsid,
        "cas": params.cas,
        "inchikey": params.inchikey,
        "name": params.name,
    }
    chemical_trace_requested = any(chemical_query.values())
    chemical_trace: dict[str, Any] | None = None
    limitations: list[str] = []
    if chemical_trace_requested:
        try:
            chemical_trace = await trace_chemical_on_draft(
                TraceChemicalOnDraftInput(
                    draft_id=params.draft_id,
                    version_id=params.version_id,
                    dtxsid=params.dtxsid,
                    cas=params.cas,
                    inchikey=params.inchikey,
                    name=params.name,
                    assay_limit=params.assay_limit,
                    min_hitcall=params.min_hitcall,
                )
            )
        except ValueError as exc:
            limitations.append(
                f"Chemical trace could not be included: {exc}"
            )
    else:
        limitations.append(
            "Chemical trace was not included because no chemical identifier was supplied."
        )

    failed_validation_messages = [
        item["message"]
        for item in validation["results"]
        if item["status"] == "fail"
    ]
    external_support = build_imported_registry_support_summary(
        version.metadata.provenance
    )
    merged_limitations = list(
        dict.fromkeys(
            [
                *failed_validation_messages,
                *quantitative_review["limitations"],
                *(chemical_trace["limitations"] if chemical_trace is not None else []),
                *external_support["limitations"],
                *limitations,
            ]
        )
    )

    payload = {
        "draft_id": quantitative_review["draft_id"],
        "version_id": quantitative_review["version_id"],
        "draft": quantitative_review["draft"],
        "review_parameters": {
            "assay_limit": params.assay_limit,
            "stressor_limit": params.stressor_limit,
            "min_hitcall": params.min_hitcall,
            "chemical_trace_requested": chemical_trace_requested,
        },
        "chemical_query": chemical_query,
        "bundle_summary": {
            "ready_for_review": validation["summary"]["ready_for_review"],
            "validator_error_count": validation["summary"]["error_count"],
            "validator_warning_count": validation["summary"]["warning_count"],
            "assay_cutoff_assessable_relationship_count": quantitative_review["summary"][
                "assessable_relationship_count"
            ],
            "assay_cutoff_discordant_relationship_count": quantitative_review["summary"][
                "discordant_relationship_count"
            ],
            "chemical_trace_included": chemical_trace is not None,
            "traced_key_event_count": (
                chemical_trace["summary"]["traced_key_event_count"]
                if chemical_trace is not None
                else 0
            ),
            "active_key_event_count": (
                chemical_trace["summary"]["active_key_event_count"]
                if chemical_trace is not None
                else 0
            ),
        },
        "validation": validation,
        "quantitative_review": quantitative_review,
        "chemical_trace": chemical_trace,
        "external_support": external_support,
        "limitations": merged_limitations,
    }
    evidence_gaps = await _build_review_draft_evidence_gaps_payload(
        draft=draft,
        version=version,
        entities=entities,
        relationships=relationships,
        bundle=payload,
        assay_limit=params.assay_limit,
        stressor_limit=params.stressor_limit,
        min_hitcall=params.min_hitcall,
    )
    evidence_gap_summary = evidence_gaps["summary"]
    payload["bundle_summary"] = evidence_gaps["bundle_summary"]
    payload["evidence_gap_summary"] = evidence_gap_summary
    payload["evidence_gaps"] = evidence_gaps
    validate_payload(
        evidence_gaps,
        namespace="read",
        name="review_draft_evidence_gaps.response.schema",
    )
    validate_payload(payload, namespace="read", name="review_draft_bundle.response.schema")
    return payload


class ReviewDraftEvidenceGapsInput(BaseModel):
    draft_id: str
    version_id: Optional[str] = None
    assay_limit: int = Field(default=5, ge=1, le=25)
    stressor_limit: int = Field(default=10, ge=1, le=50)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def review_draft_evidence_gaps(
    params: ReviewDraftEvidenceGapsInput,
) -> dict[str, Any]:
    bundle = await review_draft_bundle(
        ReviewDraftBundleInput(
            draft_id=params.draft_id,
            version_id=params.version_id,
            assay_limit=params.assay_limit,
            stressor_limit=params.stressor_limit,
            min_hitcall=params.min_hitcall,
        )
    )
    validate_payload(
        bundle["evidence_gaps"],
        namespace="read",
        name="review_draft_evidence_gaps.response.schema",
    )
    return bundle["evidence_gaps"]


async def _build_review_draft_evidence_gaps_payload(
    *,
    draft: Any,
    version: Any,
    entities: list[Any],
    relationships: list[Any],
    bundle: dict[str, Any],
    assay_limit: int,
    stressor_limit: int,
    min_hitcall: float,
) -> dict[str, Any]:
    aop_entity = next((entity for entity in entities if entity.type == "AdverseOutcomePathway"), None)
    key_events = [entity for entity in entities if entity.type == "KeyEvent"]
    kers = [rel for rel in relationships if rel.type == "KeyEventRelationship"]

    db_adapter = get_aop_db_adapter()
    assay_search_reports = await asyncio.gather(
        *(
            db_adapter.search_assays_for_key_event(
                _draft_key_event_search_record(entity),
                limit=assay_limit,
            )
            for entity in key_events
        )
    )

    validation_failures = {
        item["id"]: item
        for item in bundle["validation"]["results"]
        if item["status"] == "fail"
    }
    quantitative_relationships_by_id = {
        str(item["id"]): item
        for item in bundle["quantitative_review"]["relationships"]
        if item.get("id")
    }

    global_gaps = _build_draft_global_evidence_gaps(validation_failures)
    key_event_rows, assay_mapping_gap_count = _build_draft_key_event_evidence_gap_rows(
        key_events=key_events,
        assay_search_reports=assay_search_reports,
    )
    relationship_rows = _build_draft_relationship_evidence_gap_rows(
        kers=kers,
        quantitative_relationships_by_id=quantitative_relationships_by_id,
    )
    stressor_rows = _build_draft_stressor_evidence_gap_rows(
        stressors=bundle["quantitative_review"]["stressors"],
    )

    global_gap_count = len(global_gaps)
    key_event_gap_count = sum(len(item["gaps"]) for item in key_event_rows)
    relationship_gap_count = sum(len(item["gaps"]) for item in relationship_rows)
    stressor_gap_count = sum(len(item["gaps"]) for item in stressor_rows)
    all_gaps = (
        [*global_gaps]
        + [gap for item in key_event_rows for gap in item["gaps"]]
        + [gap for item in relationship_rows for gap in item["gaps"]]
        + [gap for item in stressor_rows for gap in item["gaps"]]
    )
    blocking_gap_count = sum(1 for gap in all_gaps if gap["severity"] == "error")
    total_gap_count = (
        global_gap_count
        + key_event_gap_count
        + relationship_gap_count
        + stressor_gap_count
    )
    advisory_gap_count = total_gap_count - blocking_gap_count

    recommendations = _build_draft_evidence_gap_recommendations(
        global_gaps=global_gaps,
        key_event_rows=key_event_rows,
        relationship_rows=relationship_rows,
        stressor_rows=stressor_rows,
    )
    limitations = list(
        dict.fromkeys(
            [
                *bundle["limitations"],
                *(
                    limitation
                    for report in assay_search_reports
                    for limitation in report.get("limitations", [])
                ),
            ]
        )
    )

    payload = {
        "draft_id": draft.draft_id,
        "version_id": version.version_id,
        "draft": {
            "aop_entity_id": aop_entity.identifier if aop_entity else None,
            "title": aop_entity.attributes.get("title") if aop_entity else draft.title,
            "adverse_outcome": aop_entity.attributes.get("adverse_outcome") if aop_entity else None,
        },
        "review_parameters": {
            "assay_limit": assay_limit,
            "stressor_limit": stressor_limit,
            "min_hitcall": min_hitcall,
        },
        "bundle_summary": {
            **bundle["bundle_summary"],
            "total_gap_count": total_gap_count,
            "blocking_gap_count": blocking_gap_count,
            "advisory_gap_count": advisory_gap_count,
        },
        "summary": {
            "ready_for_review": bundle["bundle_summary"]["ready_for_review"],
            "total_gap_count": total_gap_count,
            "blocking_gap_count": blocking_gap_count,
            "advisory_gap_count": advisory_gap_count,
            "global_gap_count": global_gap_count,
            "key_event_gap_count": key_event_gap_count,
            "relationship_gap_count": relationship_gap_count,
            "stressor_gap_count": stressor_gap_count,
            "assay_mapping_gap_count": assay_mapping_gap_count,
        },
        "global_gaps": global_gaps,
        "key_events": key_event_rows,
        "relationships": relationship_rows,
        "stressors": stressor_rows,
        "recommendations": recommendations,
        "limitations": limitations,
    }
    validate_payload(payload, namespace="read", name="review_draft_evidence_gaps.response.schema")
    return payload


class ExportDraftReviewArtifactInput(BaseModel):
    draft_id: str
    version_id: Optional[str] = None
    format: Literal["markdown", "json"] = "markdown"
    artifact_profile: Literal["review", "publication"] = "review"
    dtxsid: Optional[str] = None
    cas: Optional[str] = None
    inchikey: Optional[str] = None
    name: Optional[str] = None
    assay_limit: int = Field(default=5, ge=1, le=25)
    stressor_limit: int = Field(default=10, ge=1, le=50)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)


async def export_draft_review_artifact(
    params: ExportDraftReviewArtifactInput,
) -> dict[str, Any]:
    bundle = await review_draft_bundle(
        ReviewDraftBundleInput(
            draft_id=params.draft_id,
            version_id=params.version_id,
            dtxsid=params.dtxsid,
            cas=params.cas,
            inchikey=params.inchikey,
            name=params.name,
            assay_limit=params.assay_limit,
            stressor_limit=params.stressor_limit,
            min_hitcall=params.min_hitcall,
        )
    )
    evidence_gaps = bundle["evidence_gaps"]
    evidence_gap_summary = bundle["evidence_gap_summary"]
    section_titles = _draft_review_artifact_section_titles(params.artifact_profile)
    if params.format == "json":
        content = json.dumps(
            {
                "bundle": bundle,
                "evidence_gaps": evidence_gaps,
            },
            indent=2,
            sort_keys=False,
            ensure_ascii=True,
        )
    else:
        content = _render_draft_review_artifact_markdown_for_profile(
            bundle,
            artifact_profile=params.artifact_profile,
            evidence_gaps=evidence_gaps,
        )

    payload = {
        "format": params.format,
        "artifact_profile": params.artifact_profile,
        "filename": _build_draft_review_artifact_filename(
            params.format,
            draft_id=params.draft_id,
            artifact_profile=params.artifact_profile,
        ),
        "draft_id": bundle["draft_id"],
        "version_id": bundle["version_id"],
        "bundle_summary": bundle["bundle_summary"],
        "evidence_gap_summary": evidence_gap_summary,
        "section_titles": section_titles,
        "content": content,
    }
    validate_payload(
        payload,
        namespace="read",
        name="export_draft_review_artifact.response.schema",
    )
    return payload


class SaveDraftReviewArtifactInput(ExportDraftReviewArtifactInput):
    subdirectory: Optional[str] = None
    filename: Optional[str] = None
    overwrite: bool = False

    @field_validator("subdirectory")
    @classmethod
    def _validate_subdirectory(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_artifact_subdirectory(value)

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: Optional[str]) -> Optional[str]:
        return _validate_artifact_filename(value)


async def save_draft_review_artifact(
    params: SaveDraftReviewArtifactInput,
) -> dict[str, Any]:
    export = await export_draft_review_artifact(
        ExportDraftReviewArtifactInput(
            draft_id=params.draft_id,
            version_id=params.version_id,
            format=params.format,
            artifact_profile=params.artifact_profile,
            dtxsid=params.dtxsid,
            cas=params.cas,
            inchikey=params.inchikey,
            name=params.name,
            assay_limit=params.assay_limit,
            stressor_limit=params.stressor_limit,
            min_hitcall=params.min_hitcall,
        )
    )

    artifact_root_dir = _resolve_artifact_output_directory()
    target_dir = _resolve_artifact_output_directory(params.subdirectory)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = params.filename or export["filename"]
    target_path = target_dir / filename
    existed_before_write = target_path.exists()
    if existed_before_write and not params.overwrite:
        raise FileExistsError(
            f"Artifact file '{target_path}' already exists. Set overwrite=true to replace it."
        )

    content = export["content"]
    content_bytes = content.encode("utf-8")
    target_path.write_bytes(content_bytes)
    saved_at = _current_utc_timestamp()
    metadata_path = _artifact_metadata_path(target_path)
    relative_path = str(target_path.resolve().relative_to(artifact_root_dir))
    _, version, _, _ = _load_draft_version_graph(export["draft_id"], export["version_id"])
    content_sha256 = hashlib.sha256(content_bytes).hexdigest()
    metadata_payload = {
        "format": export["format"],
        "artifact_profile": export["artifact_profile"],
        "draft_id": export["draft_id"],
        "version_id": export["version_id"],
        "filename": target_path.name,
        "relative_path": relative_path,
        "bundle_summary": export["bundle_summary"],
        "evidence_gap_summary": export.get("evidence_gap_summary"),
        "section_titles": export["section_titles"],
        "bytes_written": len(content_bytes),
        "sha256": content_sha256,
        "saved_at": saved_at,
        "overwrote_existing_file": existed_before_write,
        "draft_version_integrity": _build_draft_version_integrity(version),
    }
    metadata_payload["artifact_integrity"] = {
        "algorithm": "sha256-v1",
        "content_sha256": content_sha256,
        "metadata_sha256": _metadata_payload_sha256(metadata_payload),
    }
    metadata_path.write_text(
        json.dumps(metadata_payload, indent=2, sort_keys=False, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    payload = {
        **metadata_payload,
        "path": str(target_path),
        "metadata_path": str(metadata_path),
        "output_directory": str(target_dir),
    }
    validate_payload(
        payload,
        namespace="write",
        name="save_draft_review_artifact.response.schema",
    )
    return payload


class ListSavedDraftReviewArtifactsInput(BaseModel):
    draft_id: Optional[str] = None
    artifact_profile: Optional[Literal["review", "publication"]] = None
    format: Optional[Literal["markdown", "json"]] = None
    subdirectory: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("subdirectory")
    @classmethod
    def _validate_subdirectory(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_artifact_subdirectory(value)


async def list_saved_draft_review_artifacts(
    params: ListSavedDraftReviewArtifactsInput,
) -> dict[str, Any]:
    artifact_root_dir = _resolve_artifact_output_directory()
    scanned_dir = _resolve_artifact_output_directory(params.subdirectory)
    results: list[dict[str, Any]] = []
    missing_metadata_count = 0
    warnings: list[str] = []

    if not scanned_dir.exists():
        warnings.append("Artifact output directory does not exist yet, so no saved draft review artifacts were found.")
        payload = {
            "results": [],
            "diagnostics": {
                "artifact_root_directory": str(artifact_root_dir),
                "scanned_directory": str(scanned_dir),
                "scanned_artifact_count": 0,
                "returned_artifact_count": 0,
                "missing_metadata_count": 0,
                "warnings": warnings,
            },
        }
        validate_payload(
            payload,
            namespace="read",
            name="list_saved_draft_review_artifacts.response.schema",
        )
        return payload

    artifact_paths = [
        path
        for path in scanned_dir.rglob("*")
        if path.is_file() and path.name.endswith((".md", ".json")) and not path.name.endswith(".meta.json")
    ]

    for artifact_path in artifact_paths:
        item = _build_saved_draft_review_artifact_index_item(
            artifact_path,
            artifact_root_dir=artifact_root_dir,
        )
        if not item["metadata_available"]:
            missing_metadata_count += 1
        integrity_status = item.get("integrity_check", {}).get("overall_status")
        if integrity_status == "failed":
            warnings.append(
                f"Integrity verification failed for saved artifact '{item['relative_path']}'."
            )
        elif integrity_status == "not_verifiable" and item["metadata_available"]:
            warnings.append(
                f"Integrity verification was incomplete for saved artifact '{item['relative_path']}'."
            )
        if params.draft_id and item.get("draft_id") != params.draft_id:
            continue
        if params.artifact_profile and item.get("artifact_profile") != params.artifact_profile:
            continue
        if params.format and item.get("format") != params.format:
            continue
        results.append(item)

    results.sort(
        key=lambda item: (
            item.get("saved_at") or "",
            item.get("relative_path") or "",
        ),
        reverse=True,
    )
    if len(results) > params.limit:
        warnings.append(
            f"Returned the newest {params.limit} saved draft review artifacts from {len(results)} matching artifacts."
        )
        results = results[: params.limit]
    if missing_metadata_count:
        warnings.append(
            f"{missing_metadata_count} saved artifact(s) did not include metadata sidecars, so some fields were inferred from the file system."
        )

    payload = {
        "results": results,
        "diagnostics": {
            "artifact_root_directory": str(artifact_root_dir),
            "scanned_directory": str(scanned_dir),
            "scanned_artifact_count": len(artifact_paths),
            "returned_artifact_count": len(results),
            "missing_metadata_count": missing_metadata_count,
            "warnings": warnings,
        },
    }
    validate_payload(
        payload,
        namespace="read",
        name="list_saved_draft_review_artifacts.response.schema",
    )
    return payload


class ExportDraftReplayPackageInput(BaseModel):
    draft_id: str
    version_id: Optional[str] = None
    artifact_path: Optional[str] = None
    artifact_relative_path: Optional[str] = None
    include_audit_records: bool = True
    audit_record_limit: int = Field(default=25, ge=0, le=100)

    @field_validator("artifact_relative_path")
    @classmethod
    def _validate_artifact_relative_path(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_artifact_relative_file_path(value)

    @model_validator(mode="after")
    def _validate_artifact_source(self) -> "ExportDraftReplayPackageInput":
        if self.artifact_path is not None and self.artifact_relative_path is not None:
            raise ValueError("Provide only one of artifact_path or artifact_relative_path")
        return self


async def export_draft_replay_package(
    params: ExportDraftReplayPackageInput,
) -> dict[str, Any]:
    draft, version, _, _ = _load_draft_version_graph(
        params.draft_id,
        params.version_id,
    )
    generated_at = _current_utc_timestamp()
    snapshot = _build_draft_snapshot_record(draft, version)
    external_support = build_imported_registry_support_summary(
        version.metadata.provenance
    )
    artifact_item: dict[str, Any] | None = None
    limitations = [
        "Replay package audit records are drawn from the process-local MCP audit buffer and may not include historical calls from prior server runs.",
        "Replay package verifies stored checksums but does not provide an immutable ledger or third-party timestamp.",
    ]

    if params.artifact_path is not None or params.artifact_relative_path is not None:
        artifact_path = _resolve_saved_artifact_path(
            artifact_path=params.artifact_path,
            artifact_relative_path=params.artifact_relative_path,
        )
        if not artifact_path.exists() or not artifact_path.is_file():
            raise FileNotFoundError(f"Saved artifact '{artifact_path}' was not found")
        artifact_item = _build_saved_draft_review_artifact_index_item(
            artifact_path,
            artifact_root_dir=_resolve_artifact_output_directory(),
        )
        if artifact_item.get("draft_id") not in {None, draft.draft_id}:
            limitations.append(
                "Attached saved artifact metadata draft_id does not match the requested draft."
            )
        if artifact_item.get("version_id") not in {None, version.version_id}:
            limitations.append(
                "Attached saved artifact metadata version_id does not match the requested draft version."
            )
        integrity_status = artifact_item.get("integrity_check", {}).get("overall_status")
        if integrity_status != "verified":
            limitations.append(
                "Attached saved artifact integrity did not fully verify."
            )

    audit_records = (
        _recent_tool_call_audit_records(params.audit_record_limit)
        if params.include_audit_records
        else []
    )
    payload = {
        "package_schema_version": "draft-replay-package.v1",
        "generated_at": generated_at,
        "draft_id": draft.draft_id,
        "version_id": version.version_id,
        "draft_snapshot": snapshot,
        "draft_integrity": {
            **verify_draft_integrity(draft),
            "selected_version": _build_draft_version_integrity(version),
        },
        "external_support": external_support,
        "saved_artifact": artifact_item,
        "audit_records": {
            "scope": "process_local_recent_records",
            "included": params.include_audit_records,
            "limit": params.audit_record_limit,
            "included_record_count": len(audit_records),
            "records": audit_records,
        },
        "limitations": limitations,
    }
    payload["package_sha256"] = _metadata_payload_sha256(payload)
    validate_payload(
        payload,
        namespace="read",
        name="export_draft_replay_package.response.schema",
    )
    return payload


class PlanLinearDraftReviewDocumentInput(BaseModel):
    draft_id: Optional[str] = None
    version_id: Optional[str] = None
    artifact_path: Optional[str] = None
    artifact_relative_path: Optional[str] = None
    artifact_profile: Literal["review", "publication"] = "publication"
    project: Optional[str] = None
    issue: Optional[str] = None
    icon: Optional[str] = ":microscope:"
    dtxsid: Optional[str] = None
    cas: Optional[str] = None
    inchikey: Optional[str] = None
    name: Optional[str] = None
    assay_limit: int = Field(default=5, ge=1, le=25)
    stressor_limit: int = Field(default=10, ge=1, le=50)
    min_hitcall: float = Field(default=0.9, ge=0.0, le=1.0)

    @field_validator("artifact_relative_path")
    @classmethod
    def _validate_artifact_relative_path(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_artifact_relative_file_path(value)

    @model_validator(mode="after")
    def _validate_source_mode(self) -> "PlanLinearDraftReviewDocumentInput":
        uses_saved_artifact = self.artifact_path is not None or self.artifact_relative_path is not None
        uses_live_draft = self.draft_id is not None
        if uses_saved_artifact == uses_live_draft:
            raise ValueError(
                "Provide either draft_id for a live export or artifact_path/artifact_relative_path for a saved artifact."
            )
        return self


async def plan_linear_draft_review_document(
    params: PlanLinearDraftReviewDocumentInput,
) -> dict[str, Any]:
    warnings: list[str] = []
    summary: dict[str, Any] | None = None
    source_record: dict[str, Any]

    if params.draft_id is not None:
        export = await export_draft_review_artifact(
            ExportDraftReviewArtifactInput(
                draft_id=params.draft_id,
                version_id=params.version_id,
                format="markdown",
                artifact_profile=params.artifact_profile,
                dtxsid=params.dtxsid,
                cas=params.cas,
                inchikey=params.inchikey,
                name=params.name,
                assay_limit=params.assay_limit,
                stressor_limit=params.stressor_limit,
                min_hitcall=params.min_hitcall,
            )
        )
        artifact_content = export["content"]
        artifact_format: Literal["markdown", "json"] = "markdown"
        artifact_title = _extract_draft_review_artifact_title(
            artifact_content,
            format_name=artifact_format,
            fallback_title=f"Scientific Draft Review: {export['draft_id']}",
        )
        summary = export["bundle_summary"]
        source_record = {
            "mode": "live_draft_export",
            "draft_id": export["draft_id"],
            "version_id": export["version_id"],
            "format": artifact_format,
            "artifact_profile": export["artifact_profile"],
            "path": None,
            "relative_path": None,
            "saved_at": None,
            "metadata_available": True,
            "metadata_path": None,
        }
        evidence_gap_summary = export.get("evidence_gap_summary")
    else:
        artifact_path = _resolve_saved_artifact_path(
            artifact_path=params.artifact_path,
            artifact_relative_path=params.artifact_relative_path,
        )
        if not artifact_path.exists() or not artifact_path.is_file():
            raise FileNotFoundError(f"Saved artifact '{artifact_path}' was not found")
        artifact_root_dir = _resolve_artifact_output_directory()
        artifact_item = _build_saved_draft_review_artifact_index_item(
            artifact_path,
            artifact_root_dir=artifact_root_dir,
        )
        artifact_content = artifact_path.read_text(encoding="utf-8")
        artifact_format = artifact_item["format"]
        artifact_title = _extract_draft_review_artifact_title(
            artifact_content,
            format_name=artifact_format,
            fallback_title=f"Draft Review Artifact: {artifact_item['filename']}",
        )
        summary = artifact_item.get("bundle_summary")
        evidence_gap_summary = artifact_item.get("evidence_gap_summary")
        source_record = {
            "mode": "saved_artifact",
            "draft_id": artifact_item.get("draft_id"),
            "version_id": artifact_item.get("version_id"),
            "format": artifact_item["format"],
            "artifact_profile": artifact_item["artifact_profile"],
            "path": artifact_item["path"],
            "relative_path": artifact_item["relative_path"],
            "saved_at": artifact_item["saved_at"],
            "metadata_available": artifact_item["metadata_available"],
            "metadata_path": artifact_item.get("metadata_path"),
        }
        if artifact_item["format"] != "markdown":
            warnings.append(
                "Saved artifact was not markdown, so the Linear handoff includes the raw artifact payload inside a fenced code block."
            )
        if artifact_item["artifact_profile"] != "publication":
            warnings.append(
                "Saved artifact did not use the publication profile, so the Linear handoff may be less polished than a publication-style export."
            )
        if not artifact_item["metadata_available"]:
            warnings.append(
                "Saved artifact metadata sidecar was unavailable, so some source fields were inferred from the file system."
            )
        integrity_check = artifact_item.get("integrity_check", {})
        if integrity_check.get("overall_status") != "verified":
            detail = "; ".join(integrity_check.get("messages", []))
            warnings.append(
                "Saved artifact integrity did not fully verify"
                + (f": {detail}" if detail else ".")
            )

    linear_content = _build_linear_review_document_markdown(
        artifact_content=artifact_content,
        artifact_format=artifact_format,
        source_record=source_record,
        summary=summary,
        warnings=warnings,
    )
    planner = LinearDocumentPlanner(default_icon=":microscope:")
    plan = planner.build_plan(
        draft_id=source_record.get("draft_id"),
        version_id=source_record.get("version_id"),
        artifact_title=artifact_title,
        artifact_markdown=linear_content,
        artifact_profile=source_record.get("artifact_profile") or params.artifact_profile,
        project=params.project,
        issue=params.issue,
        icon=params.icon,
        source_reference=source_record.get("relative_path") or source_record.get("path"),
    )
    plan_dict = plan.to_dict()
    payload = {
        "source": source_record,
        "artifact_summary": summary,
        "evidence_gap_summary": evidence_gap_summary,
        "linear_document": plan_dict,
        "suggested_create_document_arguments": {
            key: value
            for key, value in {
                "title": plan_dict["title"],
                "content": plan_dict["content"],
                "project": plan_dict["project"],
                "issue": plan_dict["issue"],
                "icon": plan_dict["icon"],
            }.items()
            if value is not None
        },
        "warnings": warnings,
    }
    validate_payload(
        payload,
        namespace="read",
        name="plan_linear_draft_review_document.response.schema",
    )
    return payload


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


class AttachRegistryHandoffToDraftInputModel(BaseModel):
    draft_id: str
    version_id: str
    author: str
    summary: str
    bundle: dict[str, Any]


async def attach_registry_handoff_to_draft(
    params: AttachRegistryHandoffToDraftInputModel,
) -> dict[str, Any]:
    write_tools = get_write_tools()
    result = write_tools.attach_registry_handoff(
        draft_id=params.draft_id,
        version_id=params.version_id,
        author=params.author,
        summary=params.summary,
        bundle=params.bundle,
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
    event_role: Optional[Literal["mie", "intermediate", "ao"]] = None
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
            event_role=params.event_role,
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

    version = _select_draft_version(draft, params.version_id)

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
    ke_with_event_role = sum(
        1
        for entity in key_events
        if entity.attributes.get("event_role") in {"mie", "intermediate", "ao"}
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
    add_check(
        "ke_event_role_coverage",
        "Key events include explicit topology roles",
        len(key_events) == 0 or ke_with_event_role == len(key_events),
        "warning",
        f"{ke_with_event_role}/{len(key_events)} key events include explicit event_role metadata.",
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

    key_event_ids = {entity.identifier for entity in key_events}
    adjacency: dict[str, list[str]] = {entity.identifier: [] for entity in key_events}
    indegree: dict[str, int] = {entity.identifier: 0 for entity in key_events}
    outdegree: dict[str, int] = {entity.identifier: 0 for entity in key_events}
    draft_ker_records: list[dict[str, Any]] = []
    for rel in kers:
        if rel.source not in key_event_ids or rel.target not in key_event_ids:
            continue
        adjacency.setdefault(rel.source, []).append(rel.target)
        indegree[rel.target] = indegree.get(rel.target, 0) + 1
        outdegree[rel.source] = outdegree.get(rel.source, 0) + 1
        draft_ker_records.append(
            {
                "upstream": {"id": rel.source},
                "downstream": {"id": rel.target},
            }
        )

    explicit_mies = sorted(
        entity.identifier
        for entity in key_events
        if entity.attributes.get("event_role") == "mie"
    )
    explicit_aos = sorted(
        entity.identifier
        for entity in key_events
        if entity.attributes.get("event_role") == "ao"
    )
    inferred_mies = (
        sorted(
            identifier
            for identifier in key_event_ids
            if outdegree.get(identifier, 0) > 0 and indegree.get(identifier, 0) == 0
        )
        if not explicit_mies
        else []
    )
    inferred_aos = (
        sorted(
            identifier
            for identifier in key_event_ids
            if indegree.get(identifier, 0) > 0 and outdegree.get(identifier, 0) == 0
        )
        if not explicit_aos
        else []
    )
    topology_mies = explicit_mies or inferred_mies
    topology_aos = explicit_aos or inferred_aos
    inference_used = bool(key_events) and (not explicit_mies or not explicit_aos)
    add_check(
        "topology_anchor_inference_used",
        "Topology validation used explicit anchors instead of graph inference",
        not inference_used,
        "warning",
        (
            "Topology validation inferred one or more anchor sets from graph degree because explicit event_role metadata was missing."
            if inference_used
            else "Topology validation used explicit event_role anchors."
        ),
    )
    add_check(
        "topology_mie_present",
        "At least one MIE anchor can be identified",
        bool(topology_mies),
        "error",
        "Add an explicit mie event_role or ensure at least one key event has zero incoming KERs and at least one outgoing KER.",
    )
    add_check(
        "topology_ao_present",
        "At least one AO anchor can be identified",
        bool(topology_aos),
        "error",
        "Add an explicit ao event_role or ensure at least one key event has zero outgoing KERs and at least one incoming KER.",
    )

    cycle_detected = _draft_graph_has_cycle(sorted(key_event_ids), adjacency)
    add_check(
        "topology_cycle_free",
        "KER graph is acyclic",
        not cycle_detected,
        "error",
        "Remove directed cycles from the draft KER graph before review.",
    )

    topology_paths: list[list[str]] = []
    if topology_mies and topology_aos and not cycle_detected:
        topology_paths = _enumerate_mie_to_ao_paths(
            topology_mies,
            topology_aos,
            draft_ker_records,
            max_paths=128,
        )
    add_check(
        "topology_mie_to_ao_path_exists",
        "At least one directed MIE-to-AO path exists",
        bool(topology_paths),
        "error",
        "Add or repair KERs so at least one directed path connects an MIE anchor to an AO anchor.",
    )

    inconsistent_anchor_ids = sorted(
        {
            *(
                entity_id
                for entity_id in explicit_mies
                if indegree.get(entity_id, 0) > 0
            ),
            *(
                entity_id
                for entity_id in explicit_aos
                if outdegree.get(entity_id, 0) > 0
            ),
        }
    )
    add_check(
        "topology_anchor_degree_consistency",
        "Explicit MIE/AO anchors have consistent graph degree",
        not inconsistent_anchor_ids,
        "warning",
        (
            "Explicit anchor roles conflict with graph degree for: "
            + ", ".join(inconsistent_anchor_ids)
            if inconsistent_anchor_ids
            else "Explicit anchor roles are consistent with graph degree."
        ),
    )

    anchored_key_events = sorted({node for path in topology_paths for node in path})
    unanchored_key_events = sorted(
        identifier for identifier in key_event_ids if identifier not in anchored_key_events
    )
    add_check(
        "topology_unanchored_key_events",
        "All key events participate in at least one MIE-to-AO path",
        not unanchored_key_events,
        "warning",
        (
            "Key events are not part of any MIE-to-AO path: "
            + ", ".join(unanchored_key_events)
            if unanchored_key_events
            else "Every key event participates in at least one MIE-to-AO path."
        ),
    )

    key_event_by_id = {entity.identifier: entity for entity in key_events}
    relationship_by_pair = {
        (rel.source, rel.target): rel
        for rel in kers
        if rel.source in key_event_ids and rel.target in key_event_ids
    }
    assessable_step_count = 0
    contradictory_steps: list[str] = []
    for path in topology_paths:
        for upstream_id, downstream_id in zip(path, path[1:]):
            rel = relationship_by_pair.get((upstream_id, downstream_id))
            if rel is None:
                continue
            upstream_label = _infer_draft_key_event_action_label(key_event_by_id.get(upstream_id))
            downstream_label = _infer_draft_key_event_action_label(key_event_by_id.get(downstream_id))
            relationship_label = _infer_draft_relationship_action_label(rel)
            upstream_sign = _action_label_to_sign(upstream_label)
            downstream_sign = _action_label_to_sign(downstream_label)
            relationship_sign = _action_label_to_sign(relationship_label)
            if upstream_sign is None or downstream_sign is None or relationship_sign is None:
                continue
            assessable_step_count += 1
            expected_sign = upstream_sign * relationship_sign
            if expected_sign != downstream_sign:
                contradictory_steps.append(
                    (
                        f"{upstream_id} ({upstream_label}) -> {rel.identifier} ({relationship_label}) -> "
                        f"{downstream_id} ({downstream_label})"
                    )
                )

    add_check(
        "topology_directional_concordance_assessable",
        "Draft exposes enough polarity metadata for directional concordance checks",
        assessable_step_count > 0,
        "warning",
        (
            f"{assessable_step_count} KER step(s) across MIE-to-AO paths exposed upstream KE, relationship, and downstream KE polarity metadata."
            if assessable_step_count > 0
            else "No MIE-to-AO KER steps exposed enough polarity metadata to assess directional concordance. Add KE directionality (for example attributes.direction_of_change) and explicit KER effect metadata (for example attributes.relationship_effect)."
        ),
    )
    add_check(
        "topology_directional_concordance",
        "Assessable KER steps are directionally concordant",
        not contradictory_steps,
        "warning",
        (
            "Directional polarity conflicts were detected for: "
            + "; ".join(contradictory_steps)
            if contradictory_steps
            else "No directional polarity contradictions were detected across assessable KER steps."
        ),
    )

    draft_assay_cutoff_records = await _build_draft_assay_cutoff_ordering_records(
        entities=entities,
        key_events=key_events,
        kers=kers,
        stressor_links=stressor_links,
    )
    assessable_assay_cutoff_records = [
        record
        for record in draft_assay_cutoff_records
        if record.get("heuristic_call") != "not_reported"
    ]
    discordant_assay_cutoff_ids = [
        str(record.get("id"))
        for record in assessable_assay_cutoff_records
        if record.get("discordant_chemical_count", 0) > 0
    ]
    if assessable_assay_cutoff_records:
        assessable_assay_cutoff_message = (
            f"{len(assessable_assay_cutoff_records)}/{len(draft_assay_cutoff_records)} draft KERs exposed linked-stressor assay-cutoff ordering evidence."
        )
    elif draft_assay_cutoff_records:
        assessable_assay_cutoff_message = draft_assay_cutoff_records[0]["basis"]
    else:
        assessable_assay_cutoff_message = (
            "No draft KERs were available for assay-cutoff ordering review."
        )
    add_check(
        "ker_assay_cutoff_ordering_assessable",
        "Draft exposes enough stressor and assay evidence for KER cutoff-ordering review",
        bool(assessable_assay_cutoff_records),
        "warning",
        assessable_assay_cutoff_message,
    )
    add_check(
        "ker_assay_cutoff_ordering",
        "Assessable draft KERs are quantitatively concordant by assay cutoff ordering",
        not discordant_assay_cutoff_ids,
        "warning",
        (
            "Assay-cutoff ordering conflicts were detected for: "
            + ", ".join(discordant_assay_cutoff_ids)
            if discordant_assay_cutoff_ids
            else (
                f"No assay-cutoff ordering conflicts were detected across {len(assessable_assay_cutoff_records)} assessable draft KERs."
                if assessable_assay_cutoff_records
                else "No discordant assay-cutoff ordering conflicts were detected because no draft KERs were assessable."
            )
        ),
    )

    error_count = sum(1 for check in checks if check["status"] == "fail" and check["severity"] == "error")
    warning_count = sum(1 for check in checks if check["status"] == "fail" and check["severity"] == "warning")
    score = max(0, 100 - error_count * 20 - warning_count * 5)

    payload = {
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
    validate_payload(payload, namespace="write", name="validate_draft_oecd.response.schema")
    return payload


def _select_draft_version(draft: Any, version_id: str | None) -> Any:
    version = draft.versions[-1]
    if version_id:
        for candidate in draft.versions:
            if candidate.version_id == version_id:
                return candidate
        raise KeyError(f"Version '{version_id}' not found in draft '{draft.draft_id}'")
    return version


def _load_draft_version_graph(
    draft_id: str,
    version_id: str | None,
) -> tuple[Any, Any, list[Any], list[Any]]:
    draft_store = get_draft_store()
    draft = draft_store.get_draft(draft_id)
    if draft is None:
        raise KeyError(f"Draft '{draft_id}' not found")
    version = _select_draft_version(draft, version_id)
    entities = list(version.graph.entities.values())
    relationships = list(version.graph.relationships.values())
    return draft, version, entities, relationships


async def _build_draft_assay_cutoff_ordering_records(
    *,
    entities: list[Any],
    key_events: list[Any],
    kers: list[Any],
    stressor_links: list[Any],
    assay_limit: int = 5,
    stressor_limit: int = 10,
    min_hitcall: float = 0.9,
) -> list[dict[str, Any]]:
    key_event_ids = {entity.identifier for entity in key_events}
    draft_ker_records = [
        {
            "id": rel.identifier,
            "upstream": {"id": rel.source},
            "downstream": {"id": rel.target},
        }
        for rel in kers
        if rel.source in key_event_ids and rel.target in key_event_ids
    ]
    stressor_records = _extract_draft_stressor_records(
        entities=entities,
        stressor_links=stressor_links,
    )
    structured_stressor_records = [
        record
        for record in stressor_records
        if record.get("dtxsid") or record.get("casrn")
    ]
    if stressor_records and not structured_stressor_records:
        return [
            {
                "id": ker_record.get("id"),
                **_not_reported_assay_cutoff_ordering(
                    "Draft stressors lacked structured CAS RN or DTXSID identifiers, so supplemental assay-cutoff ordering was not evaluated.",
                    transformation="phase4_assay_cutoff_ordering_missing_structured_draft_stressors",
                ),
            }
            for ker_record in draft_ker_records
        ]
    records = await _build_assay_cutoff_ordering_records_for_stressors(
        stressor_records=structured_stressor_records,
        key_event_details=[_draft_key_event_search_record(entity) for entity in key_events],
        ker_details=draft_ker_records,
        assay_limit=assay_limit,
        stressor_limit=stressor_limit,
        min_hitcall=min_hitcall,
    )
    return [
        {"id": ker_record.get("id"), **record}
        for ker_record, record in zip(draft_ker_records, records, strict=False)
    ]


def _extract_draft_stressor_records(
    *,
    entities: list[Any],
    stressor_links: list[Any],
) -> list[dict[str, Any]]:
    entity_by_id = {entity.identifier: entity for entity in entities}
    records_by_key: dict[tuple[str, str | None, str | None, str | None], dict[str, Any]] = {}
    for rel in stressor_links:
        stressor_entity = entity_by_id.get(rel.source)
        if stressor_entity is None or getattr(stressor_entity, "type", None) != "Stressor":
            continue
        label_value = str(stressor_entity.attributes.get("label") or "").strip() or None
        source_value = str(stressor_entity.attributes.get("source") or "").strip() or None
        identifier_value = str(stressor_entity.identifier).strip() or None
        casrn = (
            _extract_casrn_value(source_value)
            or _extract_casrn_value(identifier_value)
            or _extract_casrn_value(label_value)
        )
        dtxsid = (
            _extract_dtxsid_value(source_value)
            or _extract_dtxsid_value(identifier_value)
            or _extract_dtxsid_value(label_value)
        )
        label = label_value or source_value or identifier_value
        record = {
            "stressor_id": identifier_value,
            "label": label,
            "casrn": casrn,
            "dtxsid": dtxsid,
            "source": source_value,
            "linked_target_ids": [],
        }
        dedupe_key = (
            identifier_value or "",
            label,
            casrn,
            dtxsid,
        )
        existing = records_by_key.setdefault(dedupe_key, record)
        linked_target_ids = existing.setdefault("linked_target_ids", [])
        if rel.target not in linked_target_ids:
            linked_target_ids.append(rel.target)
    return list(records_by_key.values())


def _extract_casrn_value(value: Any) -> str | None:
    if not value:
        return None
    match = re.search(r"\b\d{2,7}-\d{2}-\d\b", str(value))
    return match.group(0) if match else None


def _extract_dtxsid_value(value: Any) -> str | None:
    if not value:
        return None
    match = re.search(r"\bDTXSID\d+\b", str(value), flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _draft_key_event_search_record(entity: Any) -> dict[str, Any]:
    record = dict(entity.attributes)
    record["id"] = entity.identifier
    return record


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _aggregate_trace_bioactivity(rows: list[dict[str, Any]]) -> dict[int, dict[str, float | None]]:
    aggregated: dict[int, dict[str, float | None]] = {}
    for row in rows:
        aeid = row.get("aeid")
        if not isinstance(aeid, int):
            continue
        hitcall = _coerce_float(row.get("hitc"))
        cutoff = _coerce_float(row.get("coff"))
        if hitcall is None:
            continue
        current = aggregated.setdefault(
            aeid,
            {"max_hitcall": hitcall, "best_activity_cutoff": cutoff},
        )
        current["max_hitcall"] = max(_coerce_float(current["max_hitcall"]) or hitcall, hitcall)
        current_cutoff = _coerce_float(current.get("best_activity_cutoff"))
        if cutoff is not None and (current_cutoff is None or cutoff < current_cutoff):
            current["best_activity_cutoff"] = cutoff
    return aggregated


async def _resolve_trace_chemical(
    params: TraceChemicalOnDraftInput,
    *,
    comptox: Any,
) -> tuple[dict[str, Any], list[str]]:
    limitations: list[str] = []
    query_order = [
        ("dtxsid", params.dtxsid),
        ("cas", params.cas),
        ("inchikey", params.inchikey),
        ("name", params.name),
    ]

    if params.dtxsid:
        try:
            matches = await asyncio.to_thread(comptox.search_equal, params.dtxsid)
        except CompToxError as exc:
            limitations.append(
                "CompTox chemical metadata lookup was unavailable, so the provided DTXSID was used without metadata enrichment."
            )
            limitations.append(f"CompTox detail: {exc}")
            return (
                {
                    "dtxsid": params.dtxsid,
                    "preferred_name": params.name,
                    "casrn": params.cas,
                    "inchikey": params.inchikey,
                    "matched_by": "dtxsid",
                },
                limitations,
            )
        if matches:
            if len(matches) > 1:
                limitations.append(
                    f"Multiple CompTox chemical matches were returned for DTXSID '{params.dtxsid}'; the first exact match was used."
                )
            return (_normalize_trace_chemical_match(matches[0], matched_by="dtxsid"), limitations)
        limitations.append(
            "No CompTox chemical metadata record was returned for the provided DTXSID, so tracing proceeded with the supplied identifier only."
        )
        return (
            {
                "dtxsid": params.dtxsid,
                "preferred_name": params.name,
                "casrn": params.cas,
                "inchikey": params.inchikey,
                "matched_by": "dtxsid",
            },
            limitations,
        )

    for field, value in query_order[1:]:
        if not value:
            continue
        try:
            match = await _lookup_trace_chemical_match(field, value, comptox=comptox)
        except CompToxError as exc:
            limitations.append(
                f"CompTox lookup by {field} was unavailable for '{value}'."
            )
            limitations.append(f"CompTox detail: {exc}")
            continue
        if match:
            return (_normalize_trace_chemical_match(match, matched_by=field), limitations)

    raise ValueError(
        "Could not resolve the supplied chemical identifiers to a CompTox DTXSID for draft tracing."
    )


async def _lookup_trace_chemical_match(
    field: str,
    value: str,
    *,
    comptox: Any,
) -> dict[str, Any] | None:
    if field == "cas":
        direct = await asyncio.to_thread(comptox.chemical_by_cas, value)
        if direct:
            return direct
    elif field == "inchikey":
        direct = await asyncio.to_thread(comptox.chemical_by_inchikey, value)
        if direct:
            return direct

    exact_matches = await asyncio.to_thread(comptox.search_equal, value)
    if exact_matches:
        return exact_matches[0]

    if field == "name":
        fuzzy_matches = await asyncio.to_thread(comptox.search, value)
        if fuzzy_matches:
            return fuzzy_matches[0]
    return None


def _normalize_trace_chemical_match(match: dict[str, Any], *, matched_by: str) -> dict[str, Any]:
    return {
        "dtxsid": match.get("dtxsid") or match.get("dtxSid"),
        "preferred_name": match.get("preferredName") or match.get("preferred_name") or match.get("name"),
        "casrn": match.get("casrn") or match.get("casRn"),
        "inchikey": match.get("inchikey") or match.get("inchiKey"),
        "matched_by": matched_by,
    }


def _draft_graph_has_cycle(
    node_ids: list[str],
    adjacency: dict[str, list[str]],
) -> bool:
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False

        visiting.add(node_id)
        for next_id in adjacency.get(node_id, []):
            if visit(next_id):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    for node_id in node_ids:
        if visit(node_id):
            return True
    return False


def _action_label_to_sign(label: str | None) -> int | None:
    if not label:
        return None
    normalized = str(label).strip().lower()
    positive_patterns = (
        "activation",
        "activate",
        "increase",
        "increased",
        "gain",
        "positive",
        "stimul",
        "induction",
        "upreg",
        "up-reg",
    )
    negative_patterns = (
        "inhibition",
        "inhibit",
        "repression",
        "repress",
        "decrease",
        "decreased",
        "loss",
        "negative",
        "suppress",
        "downreg",
        "down-reg",
    )
    if any(pattern in normalized for pattern in positive_patterns):
        return 1
    if any(pattern in normalized for pattern in negative_patterns):
        return -1
    return None


def _infer_draft_key_event_action_label(entity: Any) -> str | None:
    if entity is None:
        return None
    record = dict(entity.attributes)
    record.setdefault("title", entity.attributes.get("title"))
    record.setdefault("short_name", entity.attributes.get("short_name"))
    return _infer_action_label(record)


def _infer_draft_relationship_action_label(rel: Any) -> str | None:
    if rel is None:
        return None
    attributes = dict(rel.attributes)
    explicit_direction = (
        attributes.get("direction_of_change")
        or attributes.get("relationship_effect")
        or attributes.get("effect")
        or attributes.get("action")
        or attributes.get("polarity")
    )
    record = {
        "direction_of_change": explicit_direction,
        "title": attributes.get("title") or attributes.get("label") or attributes.get("name"),
        "short_name": attributes.get("short_name"),
    }
    return _infer_action_label(record)


def _summarize_key_event(record: dict[str, Any]) -> dict[str, Any]:
    mechanism_role = classify_key_event_role(record)
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
        "mechanism_role": mechanism_role["role"],
        "mechanism_role_rationale": mechanism_role["rationale"],
        "assay_artifact_risk": mechanism_role["artifactRisk"],
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


def _normalized_reference_token(value: Any) -> str | None:
    if value is None:
        return None
    token = re.sub(r"\s+", " ", str(value)).strip().lower()
    return token or None


def _reference_identity_key(reference: dict[str, Any]) -> tuple[str, str] | None:
    identifier = _normalized_reference_token(reference.get("identifier"))
    if identifier:
        return ("identifier", identifier)
    label = _normalized_reference_token(reference.get("label"))
    if not label:
        return None
    source = _normalized_reference_token(reference.get("source")) or "unknown"
    return ("label", f"{source}:{label}")


def _merge_reference_records(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "label": (left or {}).get("label") or (right or {}).get("label"),
        "identifier": (left or {}).get("identifier") or (right or {}).get("identifier"),
        "source": (left or {}).get("source") or (right or {}).get("source"),
    }


def _build_citation_concordance(
    upstream_record: dict[str, Any] | None,
    downstream_record: dict[str, Any] | None,
) -> dict[str, Any]:
    if not upstream_record or not downstream_record:
        return {
            "heuristic_call": "not_reported",
            "basis": (
                "Upstream or downstream key event metadata was unavailable, so citation concordance could not be derived."
            ),
            "upstream_reference_count": 0,
            "downstream_reference_count": 0,
            "shared_reference_count": 0,
            "shared_references": [],
            "provenance": [
                _make_provenance(
                    source="derived_from_ke_metadata",
                    field="citation_concordance",
                    transformation="phase3_reference_overlap_unavailable",
                    confidence="low",
                )
            ],
        }

    upstream_refs = _normalize_reference_records(upstream_record.get("references"))
    downstream_refs = _normalize_reference_records(downstream_record.get("references"))
    upstream_index: dict[tuple[str, str], dict[str, Any]] = {}
    downstream_index: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in upstream_refs:
        key = _reference_identity_key(reference)
        if key and key not in upstream_index:
            upstream_index[key] = reference
    for reference in downstream_refs:
        key = _reference_identity_key(reference)
        if key and key not in downstream_index:
            downstream_index[key] = reference

    shared_keys = [key for key in upstream_index if key in downstream_index]
    shared_references = [
        _merge_reference_records(upstream_index.get(key), downstream_index.get(key))
        for key in shared_keys
    ]
    upstream_count = len(upstream_index)
    downstream_count = len(downstream_index)
    shared_count = len(shared_references)

    if upstream_count == 0 and downstream_count == 0:
        heuristic_call = "not_reported"
        basis = (
            "Neither linked key event exposed supporting references, so citation concordance could not be evaluated."
        )
        transformation = "phase3_reference_overlap_absent"
        confidence = "low"
    elif upstream_count == 0 or downstream_count == 0:
        heuristic_call = "low"
        basis = (
            "Only one linked key event exposed supporting references, so shared-citation concordance could not be demonstrated. "
            "This is a weak supplemental heuristic and not evidence against the KER."
        )
        transformation = "phase3_reference_overlap_partial"
        confidence = "low"
    elif shared_count >= 3:
        heuristic_call = "strong"
        basis = (
            f"{shared_count} shared references were found across upstream and downstream key-event reference lists. "
            "This is supplemental citation concordance rather than proof that the same experiment measured both events together."
        )
        transformation = "phase3_reference_overlap_shared"
        confidence = "moderate"
    elif shared_count >= 1:
        heuristic_call = "moderate"
        basis = (
            f"{shared_count} shared reference{'s' if shared_count != 1 else ''} were found across upstream and downstream key-event reference lists. "
            "This is supplemental citation concordance rather than proof that the same experiment measured both events together."
        )
        transformation = "phase3_reference_overlap_shared"
        confidence = "moderate"
    else:
        heuristic_call = "low"
        basis = (
            "No shared references were found across upstream and downstream key-event reference lists. "
            "This is a weak supplemental heuristic and not evidence against the KER."
        )
        transformation = "phase3_reference_overlap_none"
        confidence = "low"

    return {
        "heuristic_call": heuristic_call,
        "basis": basis,
        "upstream_reference_count": upstream_count,
        "downstream_reference_count": downstream_count,
        "shared_reference_count": shared_count,
        "shared_references": shared_references,
        "provenance": [
            _make_provenance(
                source="derived_from_ke_metadata",
                field="citation_concordance",
                transformation=transformation,
                confidence=confidence,
            )
        ],
    }


async def _build_assay_cutoff_ordering_records(
    aop_id: str,
    *,
    key_event_details: list[dict[str, Any]],
    ker_details: list[dict[str, Any]],
    assay_limit: int = 5,
    stressor_limit: int = 10,
    min_hitcall: float = 0.9,
) -> list[dict[str, Any]]:
    db_adapter = get_aop_db_adapter()
    comptox = getattr(db_adapter, "comptox", None)
    if not comptox or not getattr(comptox, "has_api_key", False):
        return [
            _not_reported_assay_cutoff_ordering(
                "CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived.",
                transformation="phase4_assay_cutoff_ordering_missing_comptox",
            )
            for _ in ker_details
        ]
    stressor_records = await db_adapter.list_stressor_chemicals_for_aop(aop_id)
    return await _build_assay_cutoff_ordering_records_for_stressors(
        stressor_records=stressor_records,
        key_event_details=key_event_details,
        ker_details=ker_details,
        assay_limit=assay_limit,
        stressor_limit=stressor_limit,
        min_hitcall=min_hitcall,
    )


async def _build_assay_cutoff_ordering_records_for_stressors(
    *,
    stressor_records: list[dict[str, Any]],
    key_event_details: list[dict[str, Any]],
    ker_details: list[dict[str, Any]],
    assay_limit: int = 5,
    stressor_limit: int = 10,
    min_hitcall: float = 0.9,
) -> list[dict[str, Any]]:
    if not ker_details:
        return []

    db_adapter = get_aop_db_adapter()
    comptox = getattr(db_adapter, "comptox", None)
    if not comptox or not getattr(comptox, "has_api_key", False):
        return [
            _not_reported_assay_cutoff_ordering(
                "CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived.",
                transformation="phase4_assay_cutoff_ordering_missing_comptox",
            )
            for _ in ker_details
        ]

    if not stressor_records:
        return [
            _not_reported_assay_cutoff_ordering(
                "No linked AOP stressor chemicals were available, so shared chemical assay-cutoff ordering could not be derived.",
                transformation="phase4_assay_cutoff_ordering_missing_stressors",
            )
            for _ in ker_details
        ]

    try:
        key_event_reports = await asyncio.gather(
            *(
                db_adapter.search_assays_for_key_event(record, limit=assay_limit)
                for record in key_event_details
            )
        )
        ke_candidate_aeids: dict[str, list[int]] = {}
        for record, report in zip(key_event_details, key_event_reports, strict=False):
            key_event_id = record.get("id")
            if not key_event_id:
                continue
            aeids: list[int] = []
            for assay in report.get("results", []):
                aeid = assay.get("aeid")
                if aeid is None:
                    continue
                aeid_int = int(aeid)
                if aeid_int not in aeids:
                    aeids.append(aeid_int)
            ke_candidate_aeids[key_event_id] = aeids

        if not any(ke_candidate_aeids.values()):
            return [
                _not_reported_assay_cutoff_ordering(
                    "No upstream/downstream key events yielded candidate assay identifiers, so assay-cutoff ordering could not be evaluated.",
                    transformation="phase4_assay_cutoff_ordering_missing_ke_assays",
                )
                for _ in ker_details
            ]

        search_values: list[str] = []
        for stressor in stressor_records[:stressor_limit]:
            for value in (stressor.get("dtxsid"), stressor.get("casrn"), stressor.get("label")):
                normalized = str(value).strip() if value else ""
                if normalized and normalized not in search_values:
                    search_values.append(normalized)

        if not search_values:
            return [
                _not_reported_assay_cutoff_ordering(
                    "Linked stressors lacked searchable DTXSID, CAS RN, or label values, so assay-cutoff ordering could not be evaluated.",
                    transformation="phase4_assay_cutoff_ordering_missing_search_values",
                )
                for _ in ker_details
            ]

        matched_chemicals = await asyncio.gather(
            *(asyncio.to_thread(comptox.search_equal, search_value) for search_value in search_values)
        )
        matched_chemical_index: dict[str, dict[str, Any]] = {}
        for rows in matched_chemicals:
            if not rows:
                continue
            first_row = rows[0]
            dtxsid = first_row.get("dtxsid")
            if not dtxsid:
                continue
            matched_chemical_index.setdefault(
                dtxsid,
                {
                    "dtxsid": dtxsid,
                    "preferred_name": first_row.get("preferredName"),
                    "casrn": first_row.get("casrn"),
                },
            )

        if not matched_chemical_index:
            return [
                _not_reported_assay_cutoff_ordering(
                    "Linked AOP stressors could not be resolved into CompTox chemical identifiers, so assay-cutoff ordering could not be evaluated.",
                    transformation="phase4_assay_cutoff_ordering_missing_matched_chemicals",
                )
                for _ in ker_details
            ]

        bioactivity_rows = await asyncio.gather(
            *(
                asyncio.to_thread(comptox.bioactivity_data_by_dtxsid, dtxsid)
                for dtxsid in matched_chemical_index
            )
        )
        best_cutoffs_by_chemical_and_aeid: dict[str, dict[int, float]] = {}
        for dtxsid, rows in zip(matched_chemical_index, bioactivity_rows, strict=False):
            best_cutoffs_by_chemical_and_aeid[dtxsid] = _best_activity_cutoffs_by_aeid(
                rows,
                min_hitcall=min_hitcall,
            )
    except Exception:
        return [
            _not_reported_assay_cutoff_ordering(
                "CompTox assay or bioactivity lookups were unavailable while deriving supplemental assay-cutoff ordering, so this heuristic was not reported.",
                transformation="phase4_assay_cutoff_ordering_runtime_unavailable",
            )
            for _ in ker_details
        ]

    ke_cutoffs_by_chemical: dict[str, dict[str, float]] = {}
    for key_event_id, candidate_aeids in ke_candidate_aeids.items():
        if not candidate_aeids:
            ke_cutoffs_by_chemical[key_event_id] = {}
            continue
        chemical_cutoffs: dict[str, float] = {}
        for dtxsid, best_cutoffs in best_cutoffs_by_chemical_and_aeid.items():
            shared_cutoffs = [
                best_cutoffs[aeid] for aeid in candidate_aeids if aeid in best_cutoffs
            ]
            if shared_cutoffs:
                chemical_cutoffs[dtxsid] = min(shared_cutoffs)
        ke_cutoffs_by_chemical[key_event_id] = chemical_cutoffs

    return [
        _build_assay_cutoff_ordering_for_ker(
            record,
            ke_candidate_aeids=ke_candidate_aeids,
            ke_cutoffs_by_chemical=ke_cutoffs_by_chemical,
            matched_chemical_index=matched_chemical_index,
        )
        for record in ker_details
    ]


async def _build_assay_cutoff_ordering_for_get_ker(
    ker_record: dict[str, Any],
    *,
    upstream_record: dict[str, Any] | None,
    downstream_record: dict[str, Any] | None,
    assay_limit: int = 5,
    stressor_limit: int = 10,
    min_hitcall: float = 0.9,
) -> dict[str, Any]:
    referenced_aop_ids: list[str] = []
    for item in ker_record.get("referenced_aops") or []:
        identifier = str(item.get("id")).strip() if item.get("id") else ""
        if identifier and identifier not in referenced_aop_ids:
            referenced_aop_ids.append(identifier)
    if not referenced_aop_ids:
        return _not_reported_assay_cutoff_ordering(
            "This KER did not expose referenced AOP identifiers, so linked-stressor assay-cutoff ordering could not be derived.",
            transformation="phase4_assay_cutoff_ordering_missing_referenced_aops",
        )

    db_adapter = get_aop_db_adapter()
    comptox = getattr(db_adapter, "comptox", None)
    if not comptox or not getattr(comptox, "has_api_key", False):
        return _not_reported_assay_cutoff_ordering(
            "CompTox access was unavailable, so supplemental assay-cutoff ordering could not be derived for this KER.",
            transformation="phase4_assay_cutoff_ordering_missing_comptox",
        )
    stressor_record_groups = await asyncio.gather(
        *(db_adapter.list_stressor_chemicals_for_aop(aop_id) for aop_id in referenced_aop_ids)
    )
    stressor_records = [
        stressor
        for group in stressor_record_groups
        for stressor in group
    ]
    records = await _build_assay_cutoff_ordering_records_for_stressors(
        stressor_records=stressor_records,
        key_event_details=[
            record for record in (upstream_record, downstream_record) if record is not None
        ],
        ker_details=[ker_record],
        assay_limit=assay_limit,
        stressor_limit=stressor_limit,
        min_hitcall=min_hitcall,
    )
    if records:
        return records[0]
    return _not_reported_assay_cutoff_ordering(
        "No assay-cutoff ordering record could be derived for this KER.",
        transformation="phase4_assay_cutoff_ordering_missing_records",
    )


def _build_assay_cutoff_ordering_for_ker(
    record: dict[str, Any],
    *,
    ke_candidate_aeids: dict[str, list[int]],
    ke_cutoffs_by_chemical: dict[str, dict[str, float]],
    matched_chemical_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    upstream_id = (record.get("upstream") or {}).get("id")
    downstream_id = (record.get("downstream") or {}).get("id")
    upstream_candidate_aeids = ke_candidate_aeids.get(upstream_id or "", [])
    downstream_candidate_aeids = ke_candidate_aeids.get(downstream_id or "", [])

    if not upstream_candidate_aeids or not downstream_candidate_aeids:
        return {
            **_not_reported_assay_cutoff_ordering(
                "Upstream or downstream key events did not yield candidate assay identifiers with evaluable activity cutoffs.",
                transformation="phase4_assay_cutoff_ordering_missing_ke_pair_assays",
            ),
            "upstream_candidate_assay_count": len(upstream_candidate_aeids),
            "downstream_candidate_assay_count": len(downstream_candidate_aeids),
        }

    upstream_cutoffs = ke_cutoffs_by_chemical.get(upstream_id or "", {})
    downstream_cutoffs = ke_cutoffs_by_chemical.get(downstream_id or "", {})
    shared_dtxsids = sorted(set(upstream_cutoffs) & set(downstream_cutoffs))
    if not shared_dtxsids:
        return {
            **_not_reported_assay_cutoff_ordering(
                "No shared linked-stressor chemicals exposed evaluable upstream and downstream assay cutoffs for this KER.",
                transformation="phase4_assay_cutoff_ordering_missing_shared_chemicals",
            ),
            "upstream_candidate_assay_count": len(upstream_candidate_aeids),
            "downstream_candidate_assay_count": len(downstream_candidate_aeids),
        }

    supporting_chemicals: list[dict[str, Any]] = []
    concordant_chemical_count = 0
    discordant_chemical_count = 0
    for dtxsid in shared_dtxsids:
        upstream_cutoff = upstream_cutoffs[dtxsid]
        downstream_cutoff = downstream_cutoffs[dtxsid]
        ordering = "concordant" if upstream_cutoff <= downstream_cutoff else "discordant"
        if ordering == "concordant":
            concordant_chemical_count += 1
        else:
            discordant_chemical_count += 1
        chemical = matched_chemical_index.get(dtxsid, {})
        supporting_chemicals.append(
            {
                "dtxsid": dtxsid,
                "preferred_name": chemical.get("preferred_name"),
                "casrn": chemical.get("casrn"),
                "upstream_best_activity_cutoff": upstream_cutoff,
                "downstream_best_activity_cutoff": downstream_cutoff,
                "ordering": ordering,
            }
        )

    supporting_chemical_count = len(supporting_chemicals)
    if discordant_chemical_count == 0 and supporting_chemical_count >= 3:
        heuristic_call = "strong"
        transformation = "phase4_assay_cutoff_ordering_concordant"
        confidence = "moderate"
        basis = (
            f"All {supporting_chemical_count} shared linked-stressor chemicals showed upstream assay cutoffs less than or equal to downstream assay cutoffs. "
            "This is a supplemental quantitative-ordering heuristic derived from KE assay discovery plus linked-stressor bioactivity."
        )
    elif discordant_chemical_count == 0:
        heuristic_call = "moderate"
        transformation = "phase4_assay_cutoff_ordering_concordant"
        confidence = "low"
        basis = (
            f"All {supporting_chemical_count} shared linked-stressor chemical comparison{'s' if supporting_chemical_count != 1 else ''} showed upstream assay cutoffs less than or equal to downstream assay cutoffs. "
            "This is a supplemental quantitative-ordering heuristic derived from KE assay discovery plus linked-stressor bioactivity."
        )
    else:
        heuristic_call = "low"
        transformation = "phase4_assay_cutoff_ordering_mixed"
        confidence = "low"
        basis = (
            f"{concordant_chemical_count}/{supporting_chemical_count} shared linked-stressor chemicals showed upstream assay cutoffs less than or equal to downstream assay cutoffs, "
            f"while {discordant_chemical_count} showed the opposite ordering. This is a supplemental quantitative-ordering heuristic rather than a curated qAOP model."
        )

    return {
        "heuristic_call": heuristic_call,
        "basis": basis,
        "upstream_candidate_assay_count": len(upstream_candidate_aeids),
        "downstream_candidate_assay_count": len(downstream_candidate_aeids),
        "supporting_chemical_count": supporting_chemical_count,
        "concordant_chemical_count": concordant_chemical_count,
        "discordant_chemical_count": discordant_chemical_count,
        "supporting_chemicals": supporting_chemicals,
        "provenance": [
            _make_provenance(
                source="derived_from_ke_assays_and_comptox_bioactivity",
                field="assay_cutoff_ordering",
                transformation=transformation,
                confidence=confidence,
            )
        ],
    }


def _not_reported_assay_cutoff_ordering(
    basis: str,
    *,
    transformation: str,
) -> dict[str, Any]:
    return {
        "heuristic_call": "not_reported",
        "basis": basis,
        "upstream_candidate_assay_count": 0,
        "downstream_candidate_assay_count": 0,
        "supporting_chemical_count": 0,
        "concordant_chemical_count": 0,
        "discordant_chemical_count": 0,
        "supporting_chemicals": [],
        "provenance": [
            _make_provenance(
                source="derived_from_ke_assays_and_comptox_bioactivity",
                field="assay_cutoff_ordering",
                transformation=transformation,
                confidence="low",
            )
        ],
    }


def _best_activity_cutoffs_by_aeid(
    rows: list[dict[str, Any]] | Any,
    *,
    min_hitcall: float,
) -> dict[int, float]:
    best_cutoffs: dict[int, float] = {}
    for row in rows or []:
        aeid = row.get("aeid")
        cutoff = row.get("coff")
        hitcall = float(row.get("hitc") or 0.0)
        if aeid is None or cutoff is None or hitcall < min_hitcall:
            continue
        aeid_int = int(aeid)
        cutoff_float = float(cutoff)
        current = best_cutoffs.get(aeid_int)
        if current is None or cutoff_float < current:
            best_cutoffs[aeid_int] = cutoff_float
    return best_cutoffs


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
    if (
        not shared_values
        and field == "taxonomic_applicability"
        and upstream_values
        and downstream_values
    ):
        inferred_taxon = get_semantic_tools().lowest_common_taxon(
            [*upstream_values, *downstream_values]
        )
        if inferred_taxon:
            evidence_call = "moderate" if reference_count else "low"
            rationale = (
                "Derived from the lowest common taxonomic ancestor shared by upstream and downstream key-event taxa, with supporting references carried forward from the linked key events."
                if reference_count
                else "Derived from the lowest common taxonomic ancestor shared by upstream and downstream key-event taxa. The current RDF export does not expose direct KER-level applicability evidence strength."
            )
            term = _build_applicability_term(
                inferred_taxon,
                source_field=source_field,
                source="derived_from_taxonomic_lca",
                evidence_call=evidence_call,
                rationale=rationale,
            )
            if term is not None:
                term["references"] = supporting_references
                term["provenance"].append(
                    _make_provenance(
                        source="derived_from_taxonomic_lca",
                        field=source_field,
                        transformation="phase3_ker_taxonomic_lca_inference",
                        confidence="moderate" if reference_count else "low",
                    )
                )
                return [term]

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
        taxonomic_lca_inferred = any(
            provenance.get("transformation") == "phase3_ker_taxonomic_lca_inference"
            for item in taxa
            for provenance in item.get("provenance", [])
        )
        if taxa or life_stages or sexes:
            if taxonomic_lca_inferred:
                summary_rationale = (
                    "Derived conservatively from shared upstream/downstream applicability terms plus lowest-common-ancestor taxonomic inference when exact species overlap was unavailable."
                )
                transformation = "phase3_ker_applicability_taxonomic_lca"
            else:
                summary_rationale = (
                    "Derived conservatively from applicability terms shared by both upstream and downstream key events because direct KER-level applicability fields are not exposed in the current RDF export."
                )
                transformation = "phase3_ker_applicability_intersection"
            confidence = "moderate"
        else:
            summary_rationale = (
                "No shared upstream/downstream applicability terms were available to derive a conservative KER-level applicability summary."
            )
            transformation = "phase3_ker_applicability_unavailable"
            confidence = "low"
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
    assay_cutoff_ordering: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(record)
    normalized_references = _normalize_reference_records(record.get("references"))
    citation_concordance = _build_citation_concordance(upstream_record, downstream_record)
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
    normalized["citation_concordance"] = citation_concordance
    normalized["assay_cutoff_ordering"] = assay_cutoff_ordering or _not_reported_assay_cutoff_ordering(
        "Supplemental assay-cutoff ordering was not evaluated for this KER.",
        transformation="phase4_assay_cutoff_ordering_not_evaluated",
    )
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


def _summarize_ker(
    record: dict[str, Any],
    *,
    key_event_lookup: dict[str, dict[str, Any]] | None = None,
    assay_cutoff_ordering: dict[str, Any] | None = None,
) -> dict[str, Any]:
    biological_plausibility = record.get("biological_plausibility")
    empirical_support = record.get("empirical_support")
    quantitative_understanding = record.get("quantitative_understanding")
    citation_concordance = _build_citation_concordance(
        (key_event_lookup or {}).get((record.get("upstream") or {}).get("id")),
        (key_event_lookup or {}).get((record.get("downstream") or {}).get("id")),
    )
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
        "citation_concordance": citation_concordance,
        "citation_concordance_call": citation_concordance["heuristic_call"],
        "shared_reference_count": citation_concordance["shared_reference_count"],
        "assay_cutoff_ordering": assay_cutoff_ordering,
        "assay_cutoff_ordering_call": (
            assay_cutoff_ordering["heuristic_call"] if assay_cutoff_ordering else "not_reported"
        ),
        "assay_cutoff_supporting_chemical_count": (
            assay_cutoff_ordering.get("supporting_chemical_count", 0) if assay_cutoff_ordering else 0
        ),
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


def _build_supplemental_signals(
    *,
    overall_evidence: str | None,
    citation_concordance_records: list[dict[str, Any]] | None = None,
    assay_cutoff_ordering_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    overall_evidence_call = _extract_support_call(overall_evidence)
    citation_concordance_records = citation_concordance_records or []
    assay_cutoff_ordering_records = assay_cutoff_ordering_records or []
    evaluable_citation_records = [
        record
        for record in citation_concordance_records
        if record["upstream_reference_count"] > 0 or record["downstream_reference_count"] > 0
    ]
    citation_calls = [
        record["heuristic_call"]
        for record in evaluable_citation_records
        if record["heuristic_call"] != "not_reported"
    ]
    shared_reference_kers = sum(
        1 for record in citation_concordance_records if record["shared_reference_count"] > 0
    )
    total_shared_references = sum(
        record["shared_reference_count"] for record in citation_concordance_records
    )
    evaluable_assay_cutoff_records = [
        record
        for record in assay_cutoff_ordering_records
        if record.get("supporting_chemical_count", 0) > 0
    ]
    assay_cutoff_calls = [
        record["heuristic_call"]
        for record in evaluable_assay_cutoff_records
        if record["heuristic_call"] != "not_reported"
    ]
    concordant_cutoff_kers = sum(
        1
        for record in assay_cutoff_ordering_records
        if record.get("supporting_chemical_count", 0) > 0
        and record.get("discordant_chemical_count", 0) == 0
    )
    discordant_cutoff_kers = sum(
        1 for record in assay_cutoff_ordering_records if record.get("discordant_chemical_count", 0) > 0
    )
    total_cutoff_supporting_chemicals = sum(
        record.get("supporting_chemical_count", 0) for record in assay_cutoff_ordering_records
    )

    signals = {
        "aop_level_evidence_signal": {
            "heuristic_call": overall_evidence_call,
            "coverage": {"present": 1 if overall_evidence else 0, "total": 1},
            "basis": "Derived from AOP-level free-text evidence when present. This is supplemental context and not an OECD core confidence dimension.",
            "oecd_dimension": False,
        }
    }
    if citation_concordance_records:
        if shared_reference_kers > 0:
            basis = (
                f"Derived from reference-list overlap across linked upstream/downstream key events. "
                f"{shared_reference_kers}/{len(citation_concordance_records)} KERs had at least one shared reference "
                f"({total_shared_references} shared references total). This is supplemental citation concordance, not direct empirical proof."
            )
        else:
            basis = (
                "Derived from reference-list overlap across linked upstream/downstream key events. "
                "No shared references were found; this is a weak supplemental heuristic and not evidence against empirical support."
            )
        signals["citation_concordance_signal"] = {
            "heuristic_call": _aggregate_dimension_call(
                citation_calls,
                len(citation_concordance_records),
            ),
            "coverage": {
                "present": len(evaluable_citation_records),
                "total": len(citation_concordance_records),
            },
            "basis": basis,
            "oecd_dimension": False,
            "shared_reference_kers": shared_reference_kers,
            "total_shared_references": total_shared_references,
        }
    if assay_cutoff_ordering_records:
        if total_cutoff_supporting_chemicals > 0:
            basis = (
                "Derived from linked AOP stressor chemicals resolved into CompTox identifiers, key-event assay candidates, "
                f"and best observed activity cutoffs for shared chemicals across upstream/downstream KE assay sets. "
                f"{concordant_cutoff_kers}/{len(assay_cutoff_ordering_records)} KERs had only concordant shared-chemical ordering, "
                f"and {discordant_cutoff_kers} KERs showed at least one discordant comparison across {total_cutoff_supporting_chemicals} shared-chemical comparisons total. "
                "This is a supplemental quantitative-ordering heuristic, not a curated qAOP model."
            )
        else:
            basis = (
                "Linked AOP stressors, KE assay candidates, or CompTox activity cutoffs were insufficient to derive shared upstream/downstream assay-cutoff comparisons. "
                "This is a supplemental quantitative-ordering heuristic and remains not reported when the assay layer is too sparse."
            )
        signals["assay_cutoff_ordering_signal"] = {
            "heuristic_call": _aggregate_dimension_call(
                assay_cutoff_calls,
                len(assay_cutoff_ordering_records),
            ),
            "coverage": {
                "present": len(evaluable_assay_cutoff_records),
                "total": len(assay_cutoff_ordering_records),
            },
            "basis": basis,
            "oecd_dimension": False,
            "concordant_kers": concordant_cutoff_kers,
            "discordant_kers": discordant_cutoff_kers,
            "supporting_chemical_count": total_cutoff_supporting_chemicals,
        }
    return signals


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
    assay_cutoff_signal = supplemental_signals.get("assay_cutoff_ordering_signal")
    if assay_cutoff_signal:
        if assay_cutoff_signal["heuristic_call"] == "not_reported":
            limitations.append(
                "Supplemental assay-cutoff ordering could not be derived because linked stressor chemicals, KE assay candidates, or CompTox cutoff data were too sparse."
            )
        else:
            limitations.append(
                "Supplemental assay-cutoff ordering is derived heuristically from KE assay discovery plus linked-stressor CompTox bioactivity and is not a curated qAOP model."
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
