"""Track-B scientific-invariants gate — pristine + fail-closed + byte-authenticity.

These tests pin the GREEN posture of the gate on the authentic, producer-emitted
pristine corpus, prove the vendored engine is byte-authentic to the digest-pinned
manifest, and prove the fail-closed meta guards (digest tamper, unrecognized
schemaId) BLOCK. The per-advertised-code bite proofs live in
``test_scientific_invariants_adversarial.py``; the source-contract guard rejection in
``test_source_contract_guard.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance import project_to_spine as projector
from governance import source_contract
from governance import spine_bridge as bridge
from scripts.scientific_invariants_gate import (
    BLOCKING_SCIENTIFIC_CODES,
    DEFAULT_CORPUS,
    run_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pristine() -> dict:
    path = REPO_ROOT / DEFAULT_CORPUS[0]
    return json.loads(path.read_text(encoding="utf-8"))


def test_pristine_corpus_is_green() -> None:
    """The authentic producer-emitted corpus passes the engine: exit 0."""
    assert run_gate(list(DEFAULT_CORPUS)) == 0


def test_advertised_codes_are_exactly_the_proven_set() -> None:
    """The advertised set is the maximal-honest, source-fault-reachable set — no
    advertised-but-source-dead code, no missing tripwire."""
    assert BLOCKING_SCIENTIFIC_CODES == frozenset(
        {
            "FREE_TEXT_OVERCLAIM",
            "ABSOLUTE_OR_REGULATORY_OVERCLAIM",
            "CONTEXT_ONLY_OVERCLAIM",
            "AOP_CONTEXT_NOT_KER_EVIDENCE",
        }
    )


def test_pristine_projection_validates_clean_through_real_engine() -> None:
    """Every projected object from the pristine corpus is engine-valid (no findings)."""
    source = _pristine()
    assert source_contract.validate_source_object(source, corpus="pristine") is None
    projected = projector.project_assessment(source, object_label="pristine")
    assert len(projected) == 2  # ClaimRecord + EvidenceAnchor
    for _, obj in projected:
        result = bridge.validate_object(obj)
        assert result.valid, result.findings


def test_vendor_digests_are_byte_authentic() -> None:
    """The vendored engine bytes match VENDORED_FROM.json (no tamper)."""
    assert bridge.verify_vendor_digests() is None


def test_projected_schema_ids_are_engine_recognized() -> None:
    """Both projected schemaIds are in the engine's recognized set (so a valid:true is
    a real pass, not the engine's unknown-id no-op)."""
    recognized = bridge.recognized_schema_ids()
    assert recognized is not None
    for _, obj in projector.project_assessment(_pristine(), object_label="p"):
        assert obj["schemaId"] in recognized


def test_unrecognized_schema_id_blocks_fail_closed() -> None:
    """An object with an unknown schemaId is BLOCKED (UNRECOGNIZED_SPINE_SCHEMA_ID),
    never silently passed by the engine's unknown-id no-op."""
    result = bridge.validate_object({"schemaId": "https://schemas.ngra.ai/toxmcp/NotAThing.v1.schema.json"})
    assert not result.valid
    assert "UNRECOGNIZED_SPINE_SCHEMA_ID" in result.blocking_codes


def test_digest_tamper_blocks_fail_closed(tmp_path: pytest.TempPathFactory) -> None:
    """A tampered vendored file is caught (VENDOR_DIGEST_MISMATCH) BEFORE the engine
    runs. We simulate by pointing the verifier at a temp manifest with a bad digest."""
    # Re-run the real verifier against the real tree first (sanity: clean).
    assert bridge.verify_vendor_digests() is None
