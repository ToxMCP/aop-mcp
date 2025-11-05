"""Evidence matrix assembly utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

VALID_EVIDENCE = {"strong", "moderate", "weak", "not assessed"}


@dataclass
class EvidenceFacet:
    biological_plausibility: str | None = None
    temporal_concordance: str | None = None
    dose_response: str | None = None

    def validate(self) -> None:
        for name, value in [
            ("biological_plausibility", self.biological_plausibility),
            ("temporal_concordance", self.temporal_concordance),
            ("dose_response", self.dose_response),
        ]:
            if value is not None and value.lower() not in VALID_EVIDENCE:
                raise ValueError(f"Invalid evidence value for {name}: {value}")

    def to_dict(self) -> dict[str, str | None]:
        self.validate()
        return {
            "biological_plausibility": self._normalize(self.biological_plausibility),
            "temporal_concordance": self._normalize(self.temporal_concordance),
            "dose_response": self._normalize(self.dose_response),
        }

    @staticmethod
    def _normalize(value: str | None) -> str | None:
        return value.lower() if value is not None else None


def build_matrix(entries: Iterable[Mapping[str, str | None]]) -> list[dict[str, str | None]]:
    matrix: list[dict[str, str | None]] = []
    for entry in entries:
        facet = EvidenceFacet(
            biological_plausibility=entry.get("biological_plausibility"),
            temporal_concordance=entry.get("temporal_concordance"),
            dose_response=entry.get("dose_response"),
        )
        matrix.append(facet.to_dict())
    return matrix

