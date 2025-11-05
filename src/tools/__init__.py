"""Utility helpers for MCP tool responses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator



SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "schemas"


class SchemaValidationError(Exception):
    """Raised when a payload does not conform to the expected schema."""


def load_schema(namespace: str, name: str) -> dict[str, Any]:
    schema_path = SCHEMA_ROOT / namespace / f"{name}.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema '{namespace}/{name}' not found")
    return json_load(schema_path)


def json_load(path: Path) -> dict[str, Any]:
    import json

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_payload(payload: dict[str, Any], *, namespace: str, name: str) -> None:
    schema = load_schema(namespace, name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        message = "; ".join(error.message for error in errors)
        raise SchemaValidationError(message)


__all__ = ["SchemaValidationError", "validate_payload"]
