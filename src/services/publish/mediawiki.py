"""MediaWiki publish planner producing dry-run plans for AOP drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.services.draft_store import Draft, DraftVersion


@dataclass
class MediaWikiPlan:
    draft_id: str
    version_id: str
    target: str
    operations: list[Mapping[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "version_id": self.version_id,
            "target": self.target,
            "operations": self.operations,
        }


class MediaWikiPublishPlanner:
    def __init__(self, base_page_prefix: str = "AOP", dry_run: bool = True) -> None:
        self._prefix = base_page_prefix
        self._dry_run = dry_run

    def build_plan(self, draft: Draft, version: DraftVersion) -> MediaWikiPlan:
        main_page = f"{self._prefix}:{draft.draft_id}"
        summary = version.metadata.summary
        content_blocks: list[str] = []
        for entity in version.graph.entities.values():
            if entity.type == "KeyEvent":
                content_blocks.append(f"* KE {entity.identifier}: {entity.attributes.get('title', '')}")
        root_entity = version.graph.entities.get(f"AOP:{draft.draft_id}")
        description = ""
        if root_entity is not None:
            description = str(root_entity.attributes.get("description", ""))
        operations = [
            {
                "action": "update_page",
                "title": main_page,
                "summary": summary,
                "dry_run": self._dry_run,
                "content": "\n".join([
                    f"= {draft.title} =",
                    description,
                    "== Key Events ==",
                    "\n".join(content_blocks) or "(none)",
                ]),
            }
        ]
        return MediaWikiPlan(
            draft_id=draft.draft_id,
            version_id=version.version_id,
            target=main_page,
            operations=operations,
        )
