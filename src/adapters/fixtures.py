"""Utilities for loading offline fixtures used by adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "golden"


class FixtureNotFoundError(FileNotFoundError):
    """Raised when the requested fixture is unavailable."""


def load_fixture(namespace: str, name: str, *, category: str = "read") -> dict[str, Any]:
    """Load a JSON fixture from the tests/golden directory."""

    path = FIXTURE_ROOT / category / namespace / f"{name}.json"
    if not path.exists():
        raise FixtureNotFoundError(f"Fixture '{category}/{namespace}/{name}.json' not found")
    return json.loads(path.read_text(encoding="utf-8"))

