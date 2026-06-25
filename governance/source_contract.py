"""Fail-closed PRODUCER EMISSION-CONTRACT validation for the Track-B gate.

Before projecting a released aop-mcp object (the ``assess_aop_confidence.response``
confidence assessment) onto the spine, the gate MUST validate the raw source object
against the PRODUCER'S STRICT emission contract — an ``additionalProperties:false``
JSON Schema that tightens the released contract at
``docs/contracts/schemas/read/assess_aop_confidence.response.schema.json``.

The released schema is already ``additionalProperties:false`` at its top level, but
leaves several object/array members loosely typed (``{"type":"object"}``) and one
nested ``evidenceDimension`` at ``additionalProperties:true``. The STRICT contract in
``governance/contracts/assess_aop_confidence.response.strict.schema.json`` keeps the
SAME field set (so it never under- or over-claims), constrains the two load-bearing
confidence calls to the producer's four-value ladder
(``sparse_evidence`` / ``low`` / ``moderate`` / ``high``), constrains the narrative
``rationale`` / ``limitations`` arrays to string items, and constrains each
``provenance`` record to the producer's exact ``additionalProperties:false`` shape.

THE OVER-TIGHTEN TRAP, AND HOW IT WAS AVOIDED
---------------------------------------------
The released schema declares ``applicability_summary`` and ``mechanism_role_summary``
as OPTIONAL top-level fields. The strict contract was VERIFIED by running the REAL
producer (``src/server/tools/aop.py::assess_aop_confidence``) across two faithful
paths — a rich ``StubWikiAdapter`` emission (``AOP:232``) and a fixture-fallback
emission (``Aop:123``) — to confirm both fields and every required field are
populated. They are nonetheless kept OPTIONAL in the strict contract: omitting an
optional field MUST NOT falsely reject a faithful emission (the released contract
permits the omission), which is the over-tighten trap this guard refuses to fall
into.

THE OBJECTTYPE DISCRIMINATOR
----------------------------
The producer does not stamp an ``objectType`` field; the gate's corpus envelope
tags each released object with ``objectType: "assess_aop_confidence.response"`` (the
ivive-ber pattern). The strict schema requires that exact ``const`` so the guard
dispatches deterministically and an object of an unknown family is a hard block.

WHY THIS GUARD EXISTS (the dead-arm root cause it closes)
---------------------------------------------------------
A gate that projects FIRST and validates the SOURCE never (only the projected
object, or nothing) can "advertise" public-release-blocking codes whose only trigger
is a SOURCE field the producer's own strict contract cannot carry. Such a code bites
only on a hand-crafted, schema-INVALID fixture (one carrying an undeclared field) and
NEVER on an object the real producer emits — a DEAD ARM. This module is the
structural fix: every source/corpus object is validated against the strict emission
schema at the TOP of ``run_gate`` BEFORE any projection. An object that FAILS the
producer contract is a ``SOURCE_CONTRACT_VIOLATION`` meta finding that BLOCKS
(exit 1) and is NEVER projected / safe-defaulted.

FAIL-CLOSED / DEPENDENCY-FREE
-----------------------------
The validator is a small, self-contained Draft 2020-12 *subset* checker covering
exactly the keywords the emission schema uses (``type``, ``properties``, ``required``,
``enum``, ``const``, ``additionalProperties``, ``items``, ``minItems``/``maxItems``,
``minLength``/``maxLength``, ``minimum``/``maximum``/``exclusiveMinimum``/
``exclusiveMaximum``, ``multipleOf``, ``pattern``, ``format: date-time``, ``anyOf``,
``$ref`` -> ``#/$defs/...``). It depends on nothing outside the standard library, so
the guard can never be silently skipped because an optional dependency is missing. A
schema we cannot load, or a keyword we do not recognise appearing in the schema, is
itself treated as a hard block (we refuse to under-validate).
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from governance.errors import (
    SOURCE_CONTRACT_VIOLATION,
    BlockingFinding,
)

# --- the advertised meta fail-closed code -----------------------------------
#
# ``SOURCE_CONTRACT_VIOLATION`` (re-exported from ``errors``): the raw source object
# failed the producer's STRICT emission contract (additionalProperties:false JSON
# schema). BLOCKS; the object is never projected. This is the guard that closes the
# producer-emission-contract dead-arm class.
__all__ = ["SOURCE_CONTRACT_VIOLATION", "validate_source_object", "schema_for_object_type"]

# .../governance/source_contract.py -> repo root is parents[1].
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_DIR = _REPO_ROOT / "governance" / "contracts"

# objectType -> strict emission schema file. The aop-mcp gate releases exactly one
# scientific object family today (the confidence assessment); its strict contract is
# the tightened ``additionalProperties:false`` schema below.
_OBJECT_TYPE_SCHEMA: dict[str, str] = {
    "assess_aop_confidence.response": "assess_aop_confidence.response.strict.schema.json",
}

# The exact, bounded set of Draft 2020-12 keywords the emission schema uses. If a
# schema ever grows a keyword outside this set, the loader REFUSES it (fail-closed: we
# will not silently under-validate a contract we cannot fully enforce). Annotation-only
# keywords (title/description/default/examples/$id/$schema/$defs) are tolerated but not
# enforced; every CONSTRAINT keyword present below IS enforced in ``_validate``.
_SUPPORTED_KEYWORDS: frozenset[str] = frozenset(
    {
        # annotation / structural (not constraints, but legal in the schema)
        "$schema",
        "$id",
        "$defs",
        "title",
        "description",
        "default",
        "examples",
        # structural
        "$ref",
        "type",
        "properties",
        "items",
        "anyOf",
        # object constraints
        "required",
        "additionalProperties",
        # value constraints
        "enum",
        "const",
        "format",
        "pattern",
        # string constraints
        "minLength",
        "maxLength",
        # array constraints
        "minItems",
        "maxItems",
        # numeric constraints
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)

# RFC3339 date-time (the only ``format`` the schema would use for validation). Tolerant
# of an offset or a ``Z`` zone, requires a real T-separated time. A non-conforming
# string is a contract violation.
_DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


class SchemaUnsupportedError(Exception):
    """The emission schema uses a keyword the validator does not enforce.

    Raised at load time so the gate fails closed rather than under-validating.
    """


def _assert_supported(node: Any, where: str) -> None:
    """Recursively confirm every schema node uses only enforced keywords.

    Structure-aware: ``properties`` and ``$defs`` map NAMES (arbitrary, not keywords)
    to subschemas, so we recurse into their VALUES only; ``items`` is a subschema;
    ``anyOf`` is a list of subschemas; ``enum`` / ``const`` / ``required`` carry data
    values (not subschemas), so they are NOT recursed into. A subschema using any
    keyword outside ``_SUPPORTED_KEYWORDS`` is a hard fail (we refuse to under-validate).
    """
    if isinstance(node, list):
        for idx, item in enumerate(node):
            _assert_supported(item, f"{where}[{idx}]")
        return
    if not isinstance(node, dict):
        return
    for key in node:
        if key not in _SUPPORTED_KEYWORDS:
            raise SchemaUnsupportedError(
                f"Emission schema uses unsupported keyword {key!r} at {where}; "
                "the source-contract validator refuses to under-validate."
            )
    for container in ("properties", "$defs"):
        sub = node.get(container)
        if isinstance(sub, dict):
            for name, subschema in sub.items():
                _assert_supported(subschema, f"{where}.{container}.{name}")
    items = node.get("items")
    if isinstance(items, dict):
        _assert_supported(items, f"{where}.items")
    any_of = node.get("anyOf")
    if isinstance(any_of, list):
        for idx, subschema in enumerate(any_of):
            _assert_supported(subschema, f"{where}.anyOf[{idx}]")


@cache
def _load_schema(filename: str) -> dict[str, Any]:
    path = _SCHEMA_DIR / filename
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise SchemaUnsupportedError(f"Emission schema root is not an object: {filename}")
    _assert_supported(schema, "$")
    return schema


def schema_for_object_type(object_type: Any) -> str | None:
    """The strict schema filename for a released ``objectType``, or None."""
    if isinstance(object_type, str):
        return _OBJECT_TYPE_SCHEMA.get(object_type)
    return None


def _resolve_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local ``#/$defs/Name`` JSON pointer against ``root``.

    Only local pointers are supported (the strict schema is self-contained). Anything
    else is a hard fail (fail-closed).
    """
    if not ref.startswith("#/"):
        raise SchemaUnsupportedError(f"Unsupported non-local $ref: {ref!r}")
    node: Any = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            raise SchemaUnsupportedError(f"Unresolvable $ref: {ref!r}")
        node = node[token]
    if not isinstance(node, dict):
        raise SchemaUnsupportedError(f"$ref does not resolve to a schema object: {ref!r}")
    return node


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    # An unrecognised type keyword fails closed at load time, but if one slips
    # through, treat the instance as non-conforming.
    return False


def _validate(
    node: dict[str, Any], value: Any, path: str, errors: list[str], root: dict[str, Any]
) -> None:
    """Validate ``value`` against schema ``node`` (Draft 2020-12 subset), appending
    every violation message to ``errors``. ``root`` is the top schema (for $ref)."""
    # $ref: resolve and validate against the target.
    ref = node.get("$ref")
    if isinstance(ref, str):
        _validate(_resolve_ref(ref, root), value, path, errors, root)
        return

    # anyOf: the instance must validate against AT LEAST ONE branch (the strict
    # schema's nullable fields are emitted as {anyOf:[{type:string},{type:null}]}).
    any_of = node.get("anyOf")
    if isinstance(any_of, list) and any_of:
        for branch in any_of:
            if isinstance(branch, dict):
                branch_errors: list[str] = []
                _validate(branch, value, path, branch_errors, root)
                if not branch_errors:
                    break
        else:
            errors.append(f"{path}: does not match any permitted variant (anyOf)")
        return

    expected_type = node.get("type")
    if isinstance(expected_type, str) and not _type_ok(value, expected_type):
        errors.append(f"{path}: expected type {expected_type!r}")
        return  # type mismatch makes deeper checks meaningless

    if "const" in node and value != node["const"]:
        errors.append(f"{path}: expected const {node['const']!r}")

    if "enum" in node and value not in node["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {node['enum']!r}")

    if isinstance(value, str):
        min_len = node.get("minLength")
        if isinstance(min_len, int) and len(value) < min_len:
            errors.append(f"{path}: shorter than minLength {min_len}")
        max_len = node.get("maxLength")
        if isinstance(max_len, int) and len(value) > max_len:
            errors.append(f"{path}: longer than maxLength {max_len}")
        pattern = node.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            errors.append(f"{path}: does not match pattern {pattern!r}")
        if node.get("format") == "date-time" and not _DATE_TIME_RE.match(value):
            errors.append(f"{path}: not an RFC3339 date-time")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = node.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}: below minimum {minimum}")
        maximum = node.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{path}: above maximum {maximum}")
        ex_min = node.get("exclusiveMinimum")
        if isinstance(ex_min, (int, float)) and value <= ex_min:
            errors.append(f"{path}: not above exclusiveMinimum {ex_min}")
        ex_max = node.get("exclusiveMaximum")
        if isinstance(ex_max, (int, float)) and value >= ex_max:
            errors.append(f"{path}: not below exclusiveMaximum {ex_max}")
        mult = node.get("multipleOf")
        if isinstance(mult, (int, float)) and mult > 0 and (value % mult) != 0:
            errors.append(f"{path}: not a multiple of {mult}")

    if isinstance(value, dict):
        props: dict[str, Any] = node.get("properties", {}) or {}
        for req in node.get("required", []) or []:
            if req not in value:
                errors.append(f"{path}: missing required property {req!r}")
        # additionalProperties:false is the load-bearing strict guard — an undeclared
        # (root or nested) field is a contract violation here, which is exactly what
        # closes the dead-arm class.
        if node.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(
                        f"{path}: additional property {key!r} is not permitted "
                        "(producer emission contract is additionalProperties:false)"
                    )
        for key, subschema in props.items():
            if key in value and isinstance(subschema, dict):
                _validate(subschema, value[key], f"{path}.{key}", errors, root)

    if isinstance(value, list):
        min_items = node.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path}: fewer than minItems {min_items}")
        max_items = node.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path}: more than maxItems {max_items}")
        item_schema = node.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                _validate(item_schema, item, f"{path}[{idx}]", errors, root)


def validate_source_object(source: Any, *, corpus: str) -> BlockingFinding | None:
    """Validate one raw source object against the producer's STRICT emission schema.

    Dispatches on ``source.objectType`` to the strict, ``additionalProperties:false``
    contract. Returns a ``SOURCE_CONTRACT_VIOLATION`` blocking meta finding if the
    object fails the contract (including any undeclared / schema-forbidden field, since
    the schema is ``additionalProperties:false``), else ``None``.

    An object whose ``objectType`` has no known schema, or a schema we cannot
    load / fully enforce, is itself a hard block (fail-closed) — we never project an
    object whose emission contract we cannot prove.
    """
    object_type = source.get("objectType") if isinstance(source, dict) else None
    filename = schema_for_object_type(object_type)
    if filename is None:
        return BlockingFinding.meta(
            SOURCE_CONTRACT_VIOLATION,
            f"No producer emission schema for objectType {object_type!r}; "
            "refusing to project an object whose emission contract is unknown.",
            path="$.objectType",
            corpus=corpus,
        )

    try:
        schema = _load_schema(filename)
    except (OSError, json.JSONDecodeError, SchemaUnsupportedError) as exc:
        return BlockingFinding.meta(
            SOURCE_CONTRACT_VIOLATION,
            f"Producer emission schema {filename} could not be loaded/enforced: {exc}",
            path="$",
            corpus=corpus,
        )

    errors: list[str] = []
    _validate(schema, source, "$", errors, schema)
    if errors:
        return BlockingFinding.meta(
            SOURCE_CONTRACT_VIOLATION,
            f"Source object violates the producer's strict emission contract "
            f"({filename}): " + "; ".join(errors[:8]),
            path=errors[0].split(":", 1)[0] if errors else "$",
            corpus=corpus,
        )
    return None
