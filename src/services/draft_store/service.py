"""Draft store service coordinating repository operations and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .model import (
    Draft,
    DraftVersion,
    GraphEntity,
    GraphRelationship,
    GraphSnapshot,
    VersionMetadata,
    diff_graphs,
)
from src.instrumentation.logging import StructuredLogger
from .repository import DraftRepository, initialize_version


@dataclass
class CreateDraftInput:
    draft_id: str
    title: str
    author: str
    summary: str
    initial_entities: list[GraphEntity]
    initial_relationships: list[GraphRelationship]
    tags: list[str] | None = None


@dataclass
class UpdateDraftInput:
    draft_id: str
    version_id: str
    author: str
    summary: str
    entities: list[GraphEntity]
    relationships: list[GraphRelationship]
    provenance: Mapping[str, object] | None = None


class DraftStoreService:
    def __init__(self, repository: DraftRepository, logger: StructuredLogger | None = None) -> None:
        self._repo = repository
        self._logger = logger or StructuredLogger("draft-store")

    def create_draft(self, payload: CreateDraftInput) -> Draft:
        graph = GraphSnapshot(
            entities={entity.identifier: entity for entity in payload.initial_entities},
            relationships={rel.identifier: rel for rel in payload.initial_relationships},
        )
        metadata = VersionMetadata(author=payload.author, summary=payload.summary)
        version = initialize_version(payload.draft_id, "v1", graph, metadata)
        draft = Draft(
            draft_id=payload.draft_id,
            title=payload.title,
            status="draft",
            tags=list(payload.tags or []),
        )
        draft.add_version(version)
        stored = self._repo.create_draft(draft)
        self._logger.info(
            "draft_created",
            draft_id=stored.draft_id,
            version_id=stored.versions[-1].version_id,
            author=payload.author,
        )
        return stored

    def append_version(self, payload: UpdateDraftInput) -> Draft:
        current = self._repo.get_draft(payload.draft_id)
        if current is None:
            raise KeyError(f"Draft '{payload.draft_id}' not found")
        latest_graph = current.versions[-1].graph if current.versions else GraphSnapshot()
        new_graph = GraphSnapshot(
            entities={entity.identifier: entity for entity in payload.entities},
            relationships={rel.identifier: rel for rel in payload.relationships},
        )
        metadata = VersionMetadata(
            author=payload.author,
            summary=payload.summary,
            provenance=payload.provenance or {},
        )
        diff = diff_graphs(latest_graph, new_graph)
        version = DraftVersion(
            version_id=payload.version_id,
            graph=new_graph,
            metadata=metadata,
            diff=diff,
        )
        stored = self._repo.append_version(payload.draft_id, version)
        self._logger.info(
            "draft_version_appended",
            draft_id=stored.draft_id,
            version_id=version.version_id,
            author=payload.author,
        )
        return stored

    def get_draft(self, draft_id: str) -> Draft | None:
        return self._repo.get_draft(draft_id)

    def list_drafts(self) -> list[Draft]:
        return list(self._repo.list_drafts())
