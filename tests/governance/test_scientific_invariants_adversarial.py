"""Per-advertised-code bite proofs for the aop-mcp Track-B gate.

Every ADVERTISED scientific code MUST bite on a PRODUCER-CONTRACT-VALID source fault:
a fault object that (a) PASSES the strict source-contract guard (so it is something the
real producer could emit — no schema-forbidden / undeclared field, no out-of-enum
value), and (b) fires the advertised engine code through the REAL vendored bridge after
the faithful projection. A code that only bit on a contract-INVALID fixture would be a
dead arm; these tests are the proof it is not.

Each fault mutates ONLY a DECLARED producer narrative field (rationale / limitations /
aop.title / aop.abstract) of the authentic pristine emission — the exact surfaces a
future producer regression could let an overclaim or a causal/KER mislabel slip into.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from governance import project_to_spine as projector
from governance import source_contract
from governance import spine_bridge as bridge
from scripts.scientific_invariants_gate import DEFAULT_CORPUS

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pristine() -> dict:
    return json.loads((REPO_ROOT / DEFAULT_CORPUS[0]).read_text(encoding="utf-8"))


def _fired_codes(source: dict) -> set[str]:
    """Assert the fault is producer-contract-valid (guard passes), then return the set
    of engine codes that fire across the projection through the REAL bridge."""
    violation = source_contract.validate_source_object(source, corpus="adversarial")
    assert violation is None, (
        "fault must be producer-contract-VALID (else the code would be proven on a "
        f"schema-invalid fixture — a dead arm): {violation}"
    )
    fired: set[str] = set()
    for _, obj in projector.project_assessment(source, object_label="adversarial"):
        fired |= set(bridge.validate_object(obj).blocking_codes)
    return fired


def test_pristine_fires_nothing() -> None:
    assert _fired_codes(_pristine()) == set()


def test_free_text_and_absolute_overclaim_bite() -> None:
    """A safety/regulatory-acceptance overclaim smuggled into the DECLARED rationale
    narrative fires FREE_TEXT_OVERCLAIM and ABSOLUTE_OR_REGULATORY_OVERCLAIM."""
    fault = copy.deepcopy(_pristine())
    fault["rationale"] = list(fault["rationale"]) + [
        "This AOP shows the chemical is safe and regulatorily acceptable for release."
    ]
    fired = _fired_codes(fault)
    assert "FREE_TEXT_OVERCLAIM" in fired
    assert "ABSOLUTE_OR_REGULATORY_OVERCLAIM" in fired


def test_context_only_overclaim_bites() -> None:
    """A causal/adverse/risk assertion in the DECLARED limitations narrative fires
    CONTEXT_ONLY_OVERCLAIM (the assessment is interpretive context, not a causal/risk
    claim)."""
    fault = copy.deepcopy(_pristine())
    fault["limitations"] = list(fault["limitations"]) + [
        "The causal mechanism drives the adverse outcome at elevated risk."
    ]
    assert "CONTEXT_ONLY_OVERCLAIM" in _fired_codes(fault)


def test_absolute_overclaim_via_aop_abstract_bites() -> None:
    """A safety overclaim in the DECLARED aop.abstract narrative fires the free-text
    overclaim scanner — proving the projection reaches the abstract surface too."""
    fault = copy.deepcopy(_pristine())
    fault["aop"] = copy.deepcopy(fault["aop"])
    fault["aop"]["abstract"] = "The substance is harmless and poses no toxicological concern."
    assert "FREE_TEXT_OVERCLAIM" in _fired_codes(fault)


def test_aop_context_not_ker_evidence_bites() -> None:
    """KER/causal language in the DECLARED aop.title flows into the AOP context anchor's
    targetEntity and fires AOP_CONTEXT_NOT_KER_EVIDENCE — the AOP confidence assessment
    cannot be re-labelled as KER truth or primary causal evidence."""
    fault = copy.deepcopy(_pristine())
    fault["aop"] = copy.deepcopy(fault["aop"])
    fault["aop"]["title"] = "Causal key event relationship establishment for this AOP"
    assert "AOP_CONTEXT_NOT_KER_EVIDENCE" in _fired_codes(fault)


@pytest.mark.parametrize(
    "code",
    ["FREE_TEXT_OVERCLAIM", "ABSOLUTE_OR_REGULATORY_OVERCLAIM", "CONTEXT_ONLY_OVERCLAIM", "AOP_CONTEXT_NOT_KER_EVIDENCE"],
)
def test_every_advertised_code_has_a_proof(code: str) -> None:
    """Meta-assertion: every advertised code is covered by at least one bite above.

    Mirrors the BLOCKING_SCIENTIFIC_CODES set; if a code is added to the advertised set
    without a producer-contract-valid bite proof, this parametrization must be extended,
    which is the trip-wire against a silently-readded dead arm."""
    from scripts.scientific_invariants_gate import BLOCKING_SCIENTIFIC_CODES

    assert code in BLOCKING_SCIENTIFIC_CODES


def test_overclaim_is_not_launderable_by_a_negated_prefix() -> None:
    """Disguise battery: the projection's fixed claimText prefix carries NO negated
    overclaim-lexicon token, so a genuine same-word overclaim in the declared narrative
    is NOT laundered (the engine's negation scanner is global-per-field)."""
    fault = copy.deepcopy(_pristine())
    # "safe" appears in the narrative, asserted (not negated by the prefix).
    fault["rationale"] = list(fault["rationale"]) + ["The chemical is safe."]
    assert "ABSOLUTE_OR_REGULATORY_OVERCLAIM" in _fired_codes(fault)
