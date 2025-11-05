"""Semantic MCP tool implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from src.semantic import (
    ApplicabilityInput,
    ApplicabilityNormalizer,
    CurieService,
    build_matrix,
)
from src.tools import validate_payload


@dataclass
class SemanticToolConfig:
    curie_namespaces: Mapping[str, str]
    species_map: Mapping[str, str]
    life_stage_map: Mapping[str, str]
    sex_map: Mapping[str, str]


class SemanticTools:
    def __init__(self, config: SemanticToolConfig) -> None:
        self._curie_service = CurieService(config.curie_namespaces)
        self._applicability = ApplicabilityNormalizer(
            species_map=config.species_map,
            life_stage_map=config.life_stage_map,
            sex_map=config.sex_map,
            curie_service=self._curie_service,
        )

    def get_applicability(self, *, species: str | None, life_stage: str | None, sex: str | None) -> dict[str, str | None]:
        result = self._applicability.normalize(
            ApplicabilityInput(species=species, life_stage=life_stage, sex=sex)
        )
        payload = {
            "species": result.species,
            "life_stage": result.life_stage,
            "sex": result.sex,
        }
        validate_payload(payload, namespace="semantic", name="get_applicability.response.schema")
        return payload

    def get_evidence_matrix(self, entries: Iterable[Mapping[str, str | None]]) -> dict[str, list[dict[str, str | None]]]:
        matrix = build_matrix(entries)
        payload = {"matrix": matrix}
        validate_payload(payload, namespace="semantic", name="get_evidence_matrix.response.schema")
        return payload

