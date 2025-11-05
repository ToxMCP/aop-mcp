"""Write MCP tools for managing AOP drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.services.draft_store import (
    CreateDraftInput,
    DraftStoreService,
    GraphEntity,
    GraphRelationship,
    UpdateDraftInput,
)
from src.tools.semantic import SemanticTools
from src.instrumentation.logging import StructuredLogger
from src.tools import validate_payload


@dataclass
class DraftApplicability:
    species: str | None = None
    life_stage: str | None = None
    sex: str | None = None


@dataclass
class KeyEventPayload:
    identifier: str
    title: str
    event_type: str | None = None
    attributes: Mapping[str, Any] | None = None


@dataclass
class KeyEventRelationshipPayload:
    identifier: str
    upstream: str
    downstream: str
    plausibility: str | None = None
    status: str | None = None
    attributes: Mapping[str, Any] | None = None
    provenance: Mapping[str, Any] | None = None


@dataclass
class StressorLinkPayload:
    stressor_id: str
    label: str
    source: str
    target: str
    provenance: Mapping[str, Any] | None = None


class WriteTools:
    def __init__(
        self,
        draft_service: DraftStoreService,
        semantic_tools: SemanticTools | None = None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._drafts = draft_service
        self._semantic = semantic_tools
        self._logger = logger or StructuredLogger("write-tools")

    def create_draft_aop(
        self,
        *,
        draft_id: str,
        title: str,
        description: str,
        adverse_outcome: str,
        applicability: DraftApplicability | None,
        references: list[Mapping[str, Any]] | None,
        author: str,
        summary: str,
        tags: list[str] | None = None,
    ) -> dict[str, str]:
        applicability_payload: dict[str, Any] | None = None
        if self._semantic and applicability:
            normalized = self._semantic.get_applicability(
                species=applicability.species,
                life_stage=applicability.life_stage,
                sex=applicability.sex,
            )
            applicability_payload = normalized
        elif applicability:
            applicability_payload = {
                "species": applicability.species,
                "life_stage": applicability.life_stage,
                "sex": applicability.sex,
            }

        entity = GraphEntity(
            identifier=f"AOP:{draft_id}",
            type="AdverseOutcomePathway",
            attributes={
                "title": title,
                "description": description,
                "adverse_outcome": adverse_outcome,
                "applicability": applicability_payload,
                "references": references or [],
            },
        )

        draft = self._drafts.create_draft(
            CreateDraftInput(
                draft_id=draft_id,
                title=title,
                author=author,
                summary=summary,
                initial_entities=[entity],
                initial_relationships=[],
                tags=tags,
            )
        )

        response = {"draft_id": draft.draft_id, "version_id": draft.versions[-1].version_id}
        validate_payload(response, namespace="write", name="create_draft_aop.response.schema")
        self._logger.info(
            "draft_created",
            draft_id=response["draft_id"],
            version_id=response["version_id"],
            author=author,
        )
        return response

    def add_or_update_ke(
        self,
        draft_id: str,
        version_id: str,
        author: str,
        summary: str,
        payload: KeyEventPayload,
    ) -> dict[str, str]:
        draft = self._require_draft(draft_id)
        latest = draft.versions[-1].graph
        entities = dict(latest.entities)
        relationships = dict(latest.relationships)
        attributes = {
            "title": payload.title,
            "event_type": payload.event_type,
        }
        if payload.attributes:
            attributes.update(payload.attributes)
        entities[payload.identifier] = GraphEntity(
            identifier=payload.identifier,
            type="KeyEvent",
            attributes=attributes,
        )
        self._save_version(
            draft_id=draft_id,
            version_id=version_id,
            author=author,
            summary=summary,
            entities=list(entities.values()),
            relationships=list(relationships.values()),
            provenance=None,
        )
        response = {"draft_id": draft_id, "version_id": version_id}
        validate_payload(response, namespace="write", name="update_draft.response.schema")
        return response

    def add_or_update_ker(
        self,
        draft_id: str,
        version_id: str,
        author: str,
        summary: str,
        payload: KeyEventRelationshipPayload,
    ) -> dict[str, str]:
        draft = self._require_draft(draft_id)
        latest = draft.versions[-1].graph
        if payload.upstream not in latest.entities or payload.downstream not in latest.entities:
            raise ValueError("Both upstream and downstream key events must exist in the draft")
        entities = dict(latest.entities)
        relationships = dict(latest.relationships)
        attributes = {
            "plausibility": payload.plausibility,
            "status": payload.status,
        }
        if payload.attributes:
            attributes.update(payload.attributes)
        relationships[payload.identifier] = GraphRelationship(
            identifier=payload.identifier,
            source=payload.upstream,
            target=payload.downstream,
            type="KeyEventRelationship",
            attributes=attributes,
        )
        self._save_version(
            draft_id=draft_id,
            version_id=version_id,
            author=author,
            summary=summary,
            entities=list(entities.values()),
            relationships=list(relationships.values()),
            provenance=payload.provenance,
        )
        response = {"draft_id": draft_id, "version_id": version_id}
        validate_payload(response, namespace="write", name="update_draft.response.schema")
        self._logger.info(
            "draft_updated",
            draft_id=draft_id,
            version_id=version_id,
            action="add_or_update_ker",
        )
        return response

    def link_stressor(
        self,
        draft_id: str,
        version_id: str,
        author: str,
        summary: str,
        payload: StressorLinkPayload,
    ) -> dict[str, str]:
        draft = self._require_draft(draft_id)
        latest = draft.versions[-1].graph
        if payload.target not in latest.entities:
            raise ValueError("Target entity must exist before linking a stressor")
        entities = dict(latest.entities)
        relationships = dict(latest.relationships)
        stressor_entity = GraphEntity(
            identifier=payload.stressor_id,
            type="Stressor",
            attributes={"label": payload.label, "source": payload.source},
        )
        entities[payload.stressor_id] = stressor_entity
        relationships[f"STRESSOR::{payload.stressor_id}->{payload.target}"] = GraphRelationship(
            identifier=f"STRESSOR::{payload.stressor_id}->{payload.target}",
            source=payload.stressor_id,
            target=payload.target,
            type="StressorLink",
            attributes=payload.provenance or {},
        )
        self._save_version(
            draft_id=draft_id,
            version_id=version_id,
            author=author,
            summary=summary,
            entities=list(entities.values()),
            relationships=list(relationships.values()),
            provenance=payload.provenance,
        )
        response = {"draft_id": draft_id, "version_id": version_id}
        validate_payload(response, namespace="write", name="update_draft.response.schema")
        self._logger.info(
            "draft_updated",
            draft_id=draft_id,
            version_id=version_id,
            action="link_stressor",
        )
        return response

    def _require_draft(self, draft_id: str) -> Draft:
        draft = self._drafts.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"Draft '{draft_id}' not found")
        return draft

    def _save_version(
        self,
        *,
        draft_id: str,
        version_id: str,
        author: str,
        summary: str,
        entities: list[GraphEntity],
        relationships: list[GraphRelationship],
        provenance: Mapping[str, Any] | None = None,
    ) -> None:
        self._drafts.append_version(
            UpdateDraftInput(
                draft_id=draft_id,
                version_id=version_id,
                author=author,
                summary=summary,
                entities=entities,
                relationships=relationships,
                provenance=provenance,
            )
        )
