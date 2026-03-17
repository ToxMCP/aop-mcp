"""Tool handlers wiring domain services to MCP."""

from __future__ import annotations

from __future__ import annotations

import csv
import io
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from src.server.dependencies import (
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
