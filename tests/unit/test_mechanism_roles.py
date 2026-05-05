from __future__ import annotations

from src.semantic.mechanism_roles import (
    classify_key_event_role,
    summarize_mechanism_roles,
)


def test_csa_vasoconstriction_is_primary_physiological_mechanism() -> None:
    role = classify_key_event_role(
        {
            "title": "Afferent arteriolar vasoconstriction reducing renal blood flow",
            "level_of_biological_organization": "organ",
        }
    )

    assert role["role"] == "primary_physiological_mechanism"
    assert role["artifactRisk"] is False


def test_cell_injury_terms_are_downstream_with_artifact_risk() -> None:
    role = classify_key_event_role(
        {
            "title": "Mitochondrial dysfunction and apoptosis in renal tubular cells",
            "level_of_biological_organization": "cellular",
        }
    )

    assert role["role"] == "downstream_consequence"
    assert role["artifactRisk"] is True


def test_role_summary_carries_interpretation_boundary() -> None:
    summary = summarize_mechanism_roles(
        [
            {"title": "Renal vasoconstriction"},
            {"title": "Oxidative stress"},
            {"title": "Kidney failure"},
        ]
    )

    assert summary["roleCounts"]["primary_physiological_mechanism"] == 1
    assert summary["artifactRiskKeyEventCount"] == 1
    assert "must not be promoted" in summary["interpretationBoundary"]
