from __future__ import annotations

import pytest

from src.tools import validate_payload
from src.tools.semantic import SemanticToolConfig, SemanticTools


def make_tools() -> SemanticTools:
    config = SemanticToolConfig(
        curie_namespaces={
            "NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_",
            "HsapDv": "http://purl.obolibrary.org/obo/HsapDv_",
            "PATO": "http://purl.obolibrary.org/obo/PATO_",
        },
        species_map={
            "human": "NCBITaxon:9606",
            "homo sapiens": "NCBITaxon:9606",
        },
        life_stage_map={"adult": "HsapDv:0000087"},
        sex_map={"female": "PATO:0000383"},
    )
    return SemanticTools(config)


def test_get_applicability_returns_normalized_payload() -> None:
    tools = make_tools()
    payload = tools.get_applicability(species="Human", life_stage="Adult", sex="Female")
    validate_payload(payload, namespace="semantic", name="get_applicability.response.schema")
    assert payload["species"] == "NCBITaxon:9606"


def test_get_applicability_accepts_latin_species_name() -> None:
    tools = make_tools()
    payload = tools.get_applicability(species="Homo sapiens", life_stage=None, sex=None)
    assert payload["species"] == "NCBITaxon:9606"


def test_get_evidence_matrix_returns_matrix() -> None:
    tools = make_tools()
    payload = tools.get_evidence_matrix(
        [
            {
                "biological_plausibility": "strong",
                "temporal_concordance": "moderate",
                "dose_response": "not assessed",
            }
        ]
    )
    validate_payload(payload, namespace="semantic", name="get_evidence_matrix.response.schema")
    assert payload["matrix"][0]["dose_response"] == "not assessed"


def test_get_evidence_matrix_rejects_invalid_values() -> None:
    tools = make_tools()
    with pytest.raises(ValueError):
        tools.get_evidence_matrix(
            [
                {
                    "biological_plausibility": "invalid",
                    "temporal_concordance": "strong",
                    "dose_response": "weak",
                }
            ]
        )
