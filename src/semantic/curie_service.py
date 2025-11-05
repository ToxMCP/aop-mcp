"""CURIE normalization and minting utilities."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Mapping

PREFIX_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class NamespaceMap:
    prefix: str
    iri: str


class CurieService:
    def __init__(self, namespaces: Mapping[str, str], *, mint_prefix: str = "TMP") -> None:
        for prefix in namespaces:
            if not PREFIX_PATTERN.match(prefix):
                raise ValueError(f"Invalid prefix: {prefix}")
        self._namespaces = dict(namespaces)
        self._mint_prefix = mint_prefix

    def normalize(self, value: str) -> str:
        if ":" in value and value.split(":", 1)[0] in self._namespaces:
            return value
        for prefix, iri in self._namespaces.items():
            if value.startswith(iri):
                suffix = value[len(iri) :]
                return f"{prefix}:{suffix}"
        raise ValueError(f"Unknown namespace for value: {value}")

    def mint(self) -> str:
        return f"{self._mint_prefix}:{uuid.uuid4()}"

    def is_allowed_prefix(self, prefix: str) -> bool:
        return prefix in self._namespaces

