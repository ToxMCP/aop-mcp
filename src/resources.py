"""Runtime resource locations for source checkouts and installed distributions."""

from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Iterator


def resource_root(name: str, source_path: str) -> Traversable:
    bundled = files("src").joinpath("_resources", name)
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[1] / source_path


def iter_json_resources(root: Traversable, prefix: str = "") -> Iterator[tuple[str, Traversable]]:
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        relative = f"{prefix}{entry.name}"
        if entry.is_dir():
            yield from iter_json_resources(entry, f"{relative}/")
        elif entry.name.endswith(".json"):
            yield relative, entry
