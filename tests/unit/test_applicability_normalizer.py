from __future__ import annotations

import pytest

from src.semantic import ApplicabilityInput, ApplicabilityNormalizer, CurieService


def make_normalizer() -> ApplicabilityNormalizer:
    service = CurieService(
        {
            "NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_",
            "PATO": "http://purl.obolibrary.org/obo/PATO_",
            "HsapDv": "http://purl.obolibrary.org/obo/HsapDv_",
        }
    )
    return ApplicabilityNormalizer(
        species_map={"human": "NCBITaxon:9606"},
        life_stage_map={"adult": "HsapDv:0000087"},
        sex_map={"female": "PATO:0000383", "male": "PATO:0000384"},
        curie_service=service,
    )


def test_applicability_normalizer_maps_common_names() -> None:
    normalizer = make_normalizer()
    result = normalizer.normalize(ApplicabilityInput(species="Human", life_stage="adult", sex="Female"))
    assert result.species == "NCBITaxon:9606"
    assert result.life_stage == "HsapDv:0000087"
    assert result.sex == "PATO:0000383"


def test_applicability_normalizer_falls_back_to_curie() -> None:
    normalizer = make_normalizer()
    result = normalizer.normalize(ApplicabilityInput(species="NCBITaxon:10090"))
    assert result.species == "NCBITaxon:10090"
