"""Ontology migration framework for version drift protection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


class UnsupportedMigration(Exception):
    """Raised when no migration path exists between two ontology versions."""


@dataclass
class MigrationRule:
    """Single migration rule between ontology versions."""

    source_version: str
    target_version: str
    transformer: Callable[[Any], Any]
    description: str = ""


@dataclass
class OntologyMigrator:
    """Migrate data between ontology versions using registered rules."""

    migrations: Dict[str, List[MigrationRule]] = field(default_factory=dict)
    term_mappings: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def register_migration(
        self,
        source: str,
        target: str,
        transformer: Callable[[Any], Any],
        description: str = "",
    ) -> None:
        """Register a migration rule from source to target version."""
        key = f"{source}->{target}"
        self.migrations.setdefault(key, []).append(
            MigrationRule(
                source_version=source,
                target_version=target,
                transformer=transformer,
                description=description,
            )
        )

    def register_term_mapping(self, version: str, mappings: Dict[str, str]) -> None:
        """Register term remappings for a specific ontology version."""
        self.term_mappings[version] = dict(mappings)

    def migrate(self, data: Any, from_version: str, to_version: str) -> Any:
        """Migrate data from one ontology version to another."""
        if from_version == to_version:
            return data

        path = self._find_migration_path(from_version, to_version)
        if not path:
            raise UnsupportedMigration(
                f"No migration path from {from_version} to {to_version}"
            )

        result = data
        for step in path:
            result = self._apply_migration(result, step)
        return result

    def _find_migration_path(self, from_version: str, to_version: str) -> List[str]:
        """Find shortest migration path using BFS."""
        visited = {from_version}
        queue = deque([(from_version, [])])

        while queue:
            current, path = queue.popleft()
            if current == to_version:
                return path

            for key in self.migrations:
                if key.startswith(f"{current}->"):
                    next_version = key.split("->", 1)[1]
                    if next_version not in visited:
                        visited.add(next_version)
                        queue.append((next_version, path + [key]))

        return []

    def _apply_migration(self, data: Any, migration_key: str) -> Any:
        """Apply a single migration step and any term mappings."""
        for rule in self.migrations.get(migration_key, []):
            data = rule.transformer(data)

        target_version = migration_key.split("->", 1)[1]
        if target_version in self.term_mappings:
            data = self._apply_term_mappings(data, self.term_mappings[target_version])
        return data

    def _apply_term_mappings(self, data: Any, mappings: Dict[str, str]) -> Any:
        """Recursively apply term mappings to dict/list/string structures."""
        if isinstance(data, dict):
            return {
                mappings.get(k, k): self._apply_term_mappings(v, mappings)
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [self._apply_term_mappings(item, mappings) for item in data]
        if isinstance(data, str):
            return mappings.get(data, data)
        return data
