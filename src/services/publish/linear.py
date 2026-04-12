"""Linear document planner producing connector-ready review handoff payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class LinearDocumentPlan:
    draft_id: str | None
    version_id: str | None
    title: str
    content: str
    project: str | None = None
    issue: str | None = None
    icon: str | None = None
    source_reference: str | None = None
    artifact_profile: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "version_id": self.version_id,
            "title": self.title,
            "content": self.content,
            "project": self.project,
            "issue": self.issue,
            "icon": self.icon,
            "source_reference": self.source_reference,
            "artifact_profile": self.artifact_profile,
        }


class LinearDocumentPlanner:
    def __init__(self, default_icon: str = ":microscope:") -> None:
        self._default_icon = default_icon

    def build_plan(
        self,
        *,
        draft_id: str | None,
        version_id: str | None,
        artifact_title: str,
        artifact_markdown: str,
        artifact_profile: str,
        project: str | None = None,
        issue: str | None = None,
        icon: str | None = None,
        source_reference: str | None = None,
    ) -> LinearDocumentPlan:
        return LinearDocumentPlan(
            draft_id=draft_id,
            version_id=version_id,
            title=artifact_title,
            content=artifact_markdown,
            project=project,
            issue=issue,
            icon=icon if icon is not None else self._default_icon,
            source_reference=source_reference,
            artifact_profile=artifact_profile,
        )
