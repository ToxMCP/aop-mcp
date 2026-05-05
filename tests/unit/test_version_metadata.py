from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

from src.server.version import get_app_version


ROOT = Path(__file__).resolve().parents[2]


def test_package_version_metadata_is_consistent() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]

    assert version("aop-mcp-server") == project_version
    assert get_app_version() == project_version
