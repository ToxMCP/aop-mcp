"""Utilities for loading offline fixtures used by adapters."""

from __future__ import annotations

import json
from typing import Any

from src.resources import resource_root

FIXTURE_ROOT = resource_root("fixtures", "tests/golden")


class FixtureNotFoundError(FileNotFoundError):
    """Raised when the requested fixture is unavailable."""


def load_fixture(namespace: str, name: str, *, category: str = "read") -> dict[str, Any]:
    """Load a bundled offline fixture, or its canonical source-checkout copy."""

    path = FIXTURE_ROOT.joinpath(category, namespace, f"{name}.json")
    if not path.is_file():
        raise FixtureNotFoundError(f"Fixture '{category}/{namespace}/{name}.json' not found")
    return json.loads(path.read_text(encoding="utf-8"))
