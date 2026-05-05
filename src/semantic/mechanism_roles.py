"""Heuristic mechanism-role classification for AOP evidence review."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


ROLE_PRIMARY_MIE = "primary_molecular_initiating_event"
ROLE_PRIMARY_PHYSIOLOGY = "primary_physiological_mechanism"
ROLE_SECONDARY_ADAPTIVE = "secondary_adaptive_response"
ROLE_DOWNSTREAM = "downstream_consequence"
ROLE_ADVERSE_OUTCOME = "adverse_outcome"
ROLE_ARTIFACT_RISK = "assay_artifact_risk"

_VASO_TERMS = ("vasoconstrict", "vascular tone", "arteriolar", "renal blood flow", "hemodynamic")
_INJURY_TERMS = ("apoptosis", "necrosis", "oxidative stress", "mitochondrial", "ros", "nf-kb")
_ADAPTIVE_TERMS = ("inflammation", "tgf", "fibrosis", "repair", "stress response")
_AO_TERMS = ("kidney failure", "renal failure", "toxicity", "adverse outcome")


def _text(record: Mapping[str, Any]) -> str:
    parts = [
        record.get("title"),
        record.get("short_name"),
        record.get("description"),
        record.get("event_type"),
        record.get("level_of_biological_organization"),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def classify_key_event_role(record: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a key event's mechanistic role without promoting causality."""

    text = _text(record)
    event_type = str(record.get("event_type") or "").lower()
    if "molecular initiating" in event_type or "mie" == event_type:
        role = ROLE_PRIMARY_MIE
        rationale = "Event is explicitly marked as a molecular initiating event."
    elif any(term in text for term in _VASO_TERMS):
        role = ROLE_PRIMARY_PHYSIOLOGY
        rationale = "Event text indicates vascular tone or hemodynamic physiology."
    elif any(term in text for term in _AO_TERMS):
        role = ROLE_ADVERSE_OUTCOME
        rationale = "Event text indicates an adverse outcome rather than a primary mechanism."
    elif any(term in text for term in _INJURY_TERMS):
        role = ROLE_DOWNSTREAM
        rationale = "Cell injury or stress-response terms are treated as downstream unless exposure-plausible causal evidence is supplied."
    elif any(term in text for term in _ADAPTIVE_TERMS):
        role = ROLE_SECONDARY_ADAPTIVE
        rationale = "Adaptive or tissue-remodeling terms are treated as secondary pathway events."
    else:
        role = ROLE_DOWNSTREAM
        rationale = "Role is not explicit; defaulting to downstream consequence for conservative review."
    return {
        "role": role,
        "rationale": rationale,
        "artifactRisk": any(term in text for term in _INJURY_TERMS),
    }


def summarize_mechanism_roles(key_events: list[Mapping[str, Any]]) -> dict[str, Any]:
    classifications = [classify_key_event_role(record) for record in key_events]
    counts = Counter(item["role"] for item in classifications)
    artifact_count = sum(1 for item in classifications if item["artifactRisk"])
    return {
        "roleCounts": dict(sorted(counts.items())),
        "artifactRiskKeyEventCount": artifact_count,
        "interpretationBoundary": (
            "AOP key events are pathway context. Downstream oxidative stress, apoptosis, "
            "mitochondrial dysfunction, or fibrosis terms must not be promoted to a primary "
            "therapeutic-exposure mechanism without exposure-plausible KER and assay support."
        ),
    }
