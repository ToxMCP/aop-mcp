"""Repository abstractions for the draft store."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Iterable, Protocol

from .model import (
    Draft,
    DraftVersion,
    GraphSnapshot,
    VersionMetadata,
    diff_graphs,
    compute_graph_checksum,
)


class DraftRepository(Protocol):
    def create_draft(self, draft: Draft) -> Draft:
        ...

    def get_draft(self, draft_id: str) -> Draft | None:
        ...

    def list_drafts(self) -> Iterable[Draft]:
        ...

    def append_version(self, draft_id: str, version: DraftVersion) -> Draft:
        ...


class InMemoryDraftRepository(DraftRepository):
    """Simple in-memory repository appropriate for testing and prototyping."""

    def __init__(self) -> None:
        self._drafts: Dict[str, Draft] = {}

    def create_draft(self, draft: Draft) -> Draft:
        if draft.draft_id in self._drafts:
            raise ValueError(f"Draft '{draft.draft_id}' already exists")
        stored = deepcopy(draft)
        self._drafts[draft.draft_id] = stored
        return deepcopy(stored)

    def get_draft(self, draft_id: str) -> Draft | None:
        draft = self._drafts.get(draft_id)
        if draft is None:
            return None
        return deepcopy(draft)

    def list_drafts(self) -> Iterable[Draft]:
        for draft in self._drafts.values():
            yield deepcopy(draft)

    def append_version(self, draft_id: str, version: DraftVersion) -> Draft:
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise KeyError(f"Draft '{draft_id}' not found")

        stored_version = deepcopy(version)
        if draft.versions:
            previous = draft.versions[-1]
            stored_version.metadata.previous_checksum = previous.metadata.checksum
        stored_version.metadata.checksum = compute_graph_checksum(stored_version.graph)
        draft.add_version(stored_version)
        return deepcopy(draft)


def initialize_version(
    draft_id: str,
    version_id: str,
    graph: GraphSnapshot,
    metadata: VersionMetadata,
) -> DraftVersion:
    checksum = compute_graph_checksum(graph)
    metadata.checksum = checksum
    diff = diff_graphs(GraphSnapshot(), graph)
    return DraftVersion(version_id=version_id, graph=graph, metadata=metadata, diff=diff)
