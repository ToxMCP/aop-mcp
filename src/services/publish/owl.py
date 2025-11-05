"""AOPOntology OWL publish planner producing delta summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.services.draft_store import Draft, DraftVersion


@dataclass
class OWLDelta:
    draft_id: str
    version_id: str
    changes: list[Mapping[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "version_id": self.version_id,
            "changes": self.changes,
        }


class OWLPublishPlanner:
    def __init__(self, base_namespace: str = "http://aopwiki.org/graph/") -> None:
        self._base_ns = base_namespace.rstrip("/") + "/"

    def build_delta(self, draft: Draft, version: DraftVersion) -> OWLDelta:
        changes: list[Mapping[str, Any]] = []
        for entity in version.graph.entities.values():
            if entity.type == "KeyEvent":
                changes.append(
                    {
                        "action": "upsert_individual",
                        "iri": f"{self._base_ns}{entity.identifier}",
                        "type": "aopo:KeyEvent",
                        "properties": entity.attributes,
                    }
                )
            elif entity.type == "Stressor":
                changes.append(
                    {
                        "action": "upsert_individual",
                        "iri": f"{self._base_ns}{entity.identifier}",
                        "type": "aopo:Stressor",
                        "properties": entity.attributes,
                    }
                )
        for relationship in version.graph.relationships.values():
            if relationship.type == "KeyEventRelationship":
                changes.append(
                    {
                        "action": "upsert_object_property",
                        "iri": f"{self._base_ns}{relationship.identifier}",
                        "property": "aopo:has_key_event_relationship",
                        "subject": f"{self._base_ns}{relationship.source}",
                        "object": f"{self._base_ns}{relationship.target}",
                        "annotations": relationship.attributes,
                    }
                )
            elif relationship.type == "StressorLink":
                changes.append(
                    {
                        "action": "link_stressor",
                        "subject": f"{self._base_ns}{relationship.source}",
                        "object": f"{self._base_ns}{relationship.target}",
                        "annotations": relationship.attributes,
                    }
                )
        return OWLDelta(draft_id=draft.draft_id, version_id=version.version_id, changes=changes)

