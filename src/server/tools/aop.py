"""Tool handlers wiring domain services to MCP."""

from __future__ import annotations

from __future__ import annotations

from typing import Any, Optional

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
    limit: int = Field(default=10, ge=1, le=100)


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
    def ensure_identifier(cls, model: "MapChemicalInput"):  # type: ignore[override]
        if not (model.inchikey or model.cas or model.name):
            raise ValueError("Provide at least one identifier: inchikey, cas, or name")
        return model


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
