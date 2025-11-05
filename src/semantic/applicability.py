"""Applicability normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .curie_service import CurieService


@dataclass
class ApplicabilityInput:
    species: str | None = None
    life_stage: str | None = None
    sex: str | None = None


@dataclass
class ApplicabilityResult:
    species: str | None
    life_stage: str | None
    sex: str | None


class ApplicabilityNormalizer:
    def __init__(
        self,
        *,
        species_map: Mapping[str, str],
        life_stage_map: Mapping[str, str],
        sex_map: Mapping[str, str],
        curie_service: CurieService,
    ) -> None:
        self._species_map = {k.lower(): v for k, v in species_map.items()}
        self._life_stage_map = {k.lower(): v for k, v in life_stage_map.items()}
        self._sex_map = {k.lower(): v for k, v in sex_map.items()}
        self._curie_service = curie_service

    def normalize(self, data: ApplicabilityInput) -> ApplicabilityResult:
        species = self._normalize_lookup(data.species, self._species_map)
        life_stage = self._normalize_lookup(data.life_stage, self._life_stage_map)
        sex = self._normalize_lookup(data.sex, self._sex_map)
        return ApplicabilityResult(
            species=self._normalize_curie(species),
            life_stage=self._normalize_curie(life_stage),
            sex=self._normalize_curie(sex),
        )

    def _normalize_lookup(self, value: str | None, table: Mapping[str, str]) -> str | None:
        if value is None:
            return None
        key = value.strip().lower()
        return table.get(key, value)

    def _normalize_curie(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._curie_service.normalize(value)

