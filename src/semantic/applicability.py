"""Applicability normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .curie_service import CurieService


_DEFAULT_TAXON_PARENT_MAP = {
    "NCBITaxon:9606": "NCBITaxon:9605",
    "NCBITaxon:9605": "NCBITaxon:9604",
    "NCBITaxon:9604": "NCBITaxon:9443",
    "NCBITaxon:10090": "NCBITaxon:10088",
    "NCBITaxon:10088": "NCBITaxon:39107",
    "NCBITaxon:39107": "NCBITaxon:10066",
    "NCBITaxon:10066": "NCBITaxon:9989",
    "NCBITaxon:10116": "NCBITaxon:10114",
    "NCBITaxon:10114": "NCBITaxon:39107",
    "NCBITaxon:9615": "NCBITaxon:9612",
    "NCBITaxon:9612": "NCBITaxon:9608",
    "NCBITaxon:9608": "NCBITaxon:33554",
    "NCBITaxon:9989": "NCBITaxon:40674",
    "NCBITaxon:9443": "NCBITaxon:40674",
    "NCBITaxon:33554": "NCBITaxon:40674",
    "NCBITaxon:9986": "NCBITaxon:9984",
    "NCBITaxon:9984": "NCBITaxon:40674",
    "NCBITaxon:9031": "NCBITaxon:9030",
    "NCBITaxon:9030": "NCBITaxon:8782",
    "NCBITaxon:8782": "NCBITaxon:32524",
    "NCBITaxon:8457": "NCBITaxon:32524",
    "NCBITaxon:8090": "NCBITaxon:32443",
    "NCBITaxon:7955": "NCBITaxon:32443",
    "NCBITaxon:32443": "NCBITaxon:7898",
    "NCBITaxon:7898": "NCBITaxon:117570",
    "NCBITaxon:117570": "NCBITaxon:7776",
    "NCBITaxon:40674": "NCBITaxon:32524",
    "NCBITaxon:32524": "NCBITaxon:32523",
    "NCBITaxon:32523": "NCBITaxon:7776",
    "NCBITaxon:7776": "NCBITaxon:7742",
    "NCBITaxon:7742": "NCBITaxon:89593",
    "NCBITaxon:89593": "NCBITaxon:7711",
    "NCBITaxon:7227": "NCBITaxon:7215",
    "NCBITaxon:7215": "NCBITaxon:33392",
    "NCBITaxon:33392": "NCBITaxon:33208",
    "NCBITaxon:7711": "NCBITaxon:33208",
    "NCBITaxon:33208": "NCBITaxon:2759",
    "NCBITaxon:2759": "NCBITaxon:131567",
}

_DEFAULT_BLOCKED_LCA_TAXA = frozenset(
    {
        "NCBITaxon:131567",
        "NCBITaxon:2759",
        "NCBITaxon:33208",
        "NCBITaxon:7711",
    }
)


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
        taxon_parent_map: Mapping[str, str] | None = None,
        blocked_lca_taxa: Iterable[str] | None = None,
    ) -> None:
        self._species_map = {k.lower(): v for k, v in species_map.items()}
        self._life_stage_map = {k.lower(): v for k, v in life_stage_map.items()}
        self._sex_map = {k.lower(): v for k, v in sex_map.items()}
        self._curie_service = curie_service
        raw_parent_map = taxon_parent_map or _DEFAULT_TAXON_PARENT_MAP
        self._taxon_parent_map = {
            self._normalize_curie(child) or child: self._normalize_curie(parent) or parent
            for child, parent in raw_parent_map.items()
        }
        self._blocked_lca_taxa = frozenset(
            self._normalize_curie(value) or value
            for value in (blocked_lca_taxa or _DEFAULT_BLOCKED_LCA_TAXA)
        )

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

    def lowest_common_taxon(self, values: Iterable[str]) -> str | None:
        normalized_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = self._normalize_curie(value)
            if normalized and normalized not in seen:
                seen.add(normalized)
                normalized_values.append(normalized)

        if len(normalized_values) < 2:
            return normalized_values[0] if normalized_values else None

        lineages = [self._taxon_lineage(value) for value in normalized_values]
        if not all(lineages):
            return None

        for candidate in lineages[0]:
            if candidate in self._blocked_lca_taxa:
                continue
            if all(candidate in lineage for lineage in lineages[1:]):
                return candidate
        return None

    def _taxon_lineage(self, value: str) -> list[str]:
        lineage: list[str] = []
        current = value
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            lineage.append(current)
            current = self._taxon_parent_map.get(current)
        return lineage
