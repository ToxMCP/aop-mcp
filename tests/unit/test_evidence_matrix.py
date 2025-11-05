from __future__ import annotations

import pytest

from src.semantic import EvidenceFacet, build_matrix


def test_evidence_facet_normalizes_values() -> None:
    facet = EvidenceFacet(
        biological_plausibility="Strong",
        temporal_concordance="Moderate",
        dose_response="Not Assessed",
    )
    assert facet.to_dict() == {
        "biological_plausibility": "strong",
        "temporal_concordance": "moderate",
        "dose_response": "not assessed",
    }


def test_build_matrix_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        build_matrix([
            {
                "biological_plausibility": "invalid",
                "temporal_concordance": "strong",
                "dose_response": "weak",
            }
        ])


def test_build_matrix_returns_list_of_dicts() -> None:
    matrix = build_matrix(
        [
            {
                "biological_plausibility": "strong",
                "temporal_concordance": "weak",
                "dose_response": "moderate",
            }
        ]
    )
    assert matrix[0]["temporal_concordance"] == "weak"
