#!/usr/bin/env python3
"""Track-B scientific-invariants gate (vendored schema-spine engine) for aop-mcp.

Projects each RELEASED aop-mcp ``assess_aop_confidence.response`` (an AOP confidence
assessment — the anti-overclaim / confidence-ceiling / context-handoff seam of the
read surface) onto its canonical ToxMCP schema-spine shapes, runs the vendored,
digest-pinned spine policy engine over the projection via a fail-closed Node bridge,
aggregates every blocking finding, and EXITS NON-ZERO if any release-blocking code
fires.

aop-mcp's confidence assessment is a DETERMINISTIC, zero-LLM heuristic over the
AOP-Wiki RDF export (``overall_call == heuristic_overall_call``; provenance
``phase1_oecd_alignment_normalization``), and it natively issues an interpretive,
NON-causal, NON-regulatory conclusion. So on the PRISTINE corpus this gate is GREEN.
Its job is to BLOCK if a future change ever lets one of these regressions into a
released assessment:

  Scientific (from the engine), the ADVERTISED set — every one re-proven to bite on a
  PRODUCER-CONTRACT-VALID source fault (jsonschema-valid against the strict emission
  contract), each plumbed from a DECLARED producer field (see ADR-0002 and
  tests/governance/test_scientific_invariants_adversarial.py):
    FREE_TEXT_OVERCLAIM                 <- safety overclaim in the DECLARED narrative
                                           (rationale / limitations / aop title|abstract)
    ABSOLUTE_OR_REGULATORY_OVERCLAIM    <- safety/regulatory-acceptance overclaim in narrative
    CONTEXT_ONLY_OVERCLAIM              <- causal/adverse/risk/safe assertion in the
                                           DECLARED narrative (held at context_only class)
    AOP_CONTEXT_NOT_KER_EVIDENCE        <- AOP context handoff mislabeled as KER truth /
                                           primary causal evidence (ker/causal language in
                                           the DECLARED aop.title flows into the anchor's
                                           targetEntity)

  Meta fail-closed (synthesized by the source-contract guard / bridge / projection):
    SOURCE_CONTRACT_VIOLATION, ENGINE_UNAVAILABLE, UNRECOGNIZED_SPINE_SCHEMA_ID,
    VENDOR_DIGEST_MISMATCH, PROJECTION_INCOMPLETE

HONEST N/A (see ADR-0002):
  * AI-provenance arm: aop-mcp's confidence assessment is deterministic / zero-LLM
    (no AI/extraction/agent-provenance field on any released ``*.response`` object).
    The agent scaffold (src/agent/workflows.py) is a dry-run publish-plan orchestrator
    whose output never enters a released object. The gate projects no AssessmentRun
    and advertises no AI code; the deterministic N/A is documented in the ADR.
  * HIGH-CLAIM review codes dispatch only on a HIGH-STAKES claimClass; the producer
    never asserts such a class, so they are HONEST-DROPPED, not advertised-but-dead.
  * The context_only STRUCTURAL guardrails the projection itself satisfies on EVERY
    emission — ONTOLOGY_CONFIDENCE_CEILING_EXCEEDED (support capped <= weak),
    CONTEXT_ONLY_BAD_DOWNSTREAM_USE and CONTEXT_ONLY_PROHIBITIONS_REQUIRED (the
    allowed/prohibited downstream-use sets are fixed structural posture, not driven by
    any declared source field) — are NOT advertised: no producer-contract-valid SOURCE
    fault can drive them through the faithful projection, so advertising them would be
    an advertised-but-source-dead arm. They remain ENFORCED (the engine still runs them
    over every projected object, so a projection regression would still BLOCK); they are
    simply not claimed as source-fault tripwires. Documented in the ADR.

This gate is ADVISORY on the free-plan repo (no required-status-checks). It is
ADDITIVE: it touches no producer ``src/`` and no released contract, so the existing
schema-validation / smoke / read-regression gates are untouched.

Exit codes:
    0 — every projected object passed the engine (no blocking code fired)
    1 — at least one blocking code fired (release-blocking regression)
    2 — usage / corpus-loading error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from governance import project_to_spine as projector  # noqa: E402
from governance import source_contract  # noqa: E402
from governance import spine_bridge as bridge  # noqa: E402
from governance.errors import (  # noqa: E402
    PROJECTION_INCOMPLETE,
    BlockingFinding,
    ProjectionIncompleteError,
)

# --- corpus ------------------------------------------------------------------
# Each entry is a relative path to a RELEASED assess_aop_confidence.response object
# (carrying the gate's objectType envelope). The gate FAILS (exit 2) if a declared
# corpus file is missing, so the corpus cannot silently shrink.

DEFAULT_CORPUS: tuple[str, ...] = (
    # The authentic, FULL producer-emitted assessment, captured by running the real
    # producer over the StubWikiAdapter (AOP:232) and stamping the objectType tag.
    # Regenerate via scripts/build_spine_projection_goldens.py.
    "governance/fixtures/assess_aop_confidence.pristine.json",
)

# The advertised release-blocking scientific codes — the MAXIMAL set that bites on a
# PRODUCER-CONTRACT-VALID source fault (jsonschema-valid against the strict emission
# contract -> a real engine exit through this gate), each plumbed from a DECLARED
# producer field. No over-advertise, no dead arms. (Meta codes from
# errors.META_FAIL_CLOSED_CODES are ALWAYS blocking and need no listing.)
BLOCKING_SCIENTIFIC_CODES: frozenset[str] = frozenset(
    {
        "FREE_TEXT_OVERCLAIM",
        "ABSOLUTE_OR_REGULATORY_OVERCLAIM",
        "CONTEXT_ONLY_OVERCLAIM",
        "AOP_CONTEXT_NOT_KER_EVIDENCE",
    }
)


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def run_gate(corpus: list[str], *, emit_json: bool = False) -> int:
    findings: list[tuple[str, BlockingFinding]] = []
    checked = 0
    for rel in corpus:
        path = REPO_ROOT / rel
        if not path.exists():
            print(f"[scientific-invariants] FAIL: corpus file missing: {rel}", file=sys.stderr)
            return 2
        source = _load(path)

        # SOURCE-CONTRACT GUARD (fail-closed, BEFORE any projection). A packet that
        # violates the producer's STRICT emission contract (the
        # additionalProperties:false tightening of the released response schema)
        # BLOCKS and is NEVER projected — so a "fault" that could only fire a
        # scientific code by carrying a schema-forbidden / undeclared field (or an
        # out-of-enum value the producer cannot emit) is caught here as a contract
        # violation instead of silently exercising a dead arm.
        contract_violation = source_contract.validate_source_object(source, corpus=rel)
        if contract_violation is not None:
            findings.append((rel, contract_violation))
            continue

        try:
            projected = projector.project_assessment(source, object_label=rel)
        except ProjectionIncompleteError as exc:
            findings.append(
                (
                    rel,
                    BlockingFinding.meta(
                        PROJECTION_INCOMPLETE, exc.message, path=exc.path, corpus=rel
                    ),
                )
            )
            continue

        for label, obj in projected:
            checked += 1
            result = bridge.validate_object(obj)
            for finding in result.findings:
                findings.append((label, finding))

    # SAFE-BY-DEFAULT: every meta finding blocks, AND every scientific finding blocks
    # (a scientific code the engine emits over a projected object is, by construction,
    # a real invariant violation). The advertised allowlist above is documentation; we
    # do not silently drop an unlisted engine code.
    blocking = list(findings)

    if emit_json:
        print(
            json.dumps(
                {
                    "checkedObjects": checked,
                    "advertisedCodes": sorted(BLOCKING_SCIENTIFIC_CODES),
                    "blocking": [
                        {"object": label, **f.as_dict()} for (label, f) in blocking
                    ],
                    "allFindings": [
                        {"object": label, **f.as_dict()} for (label, f) in findings
                    ],
                },
                indent=2,
            )
        )

    if blocking:
        print(
            f"[scientific-invariants] BLOCK — {len(blocking)} release-blocking "
            f"finding(s) across {checked} projected object(s):",
            file=sys.stderr,
        )
        for label, f in blocking:
            print(f"  - [{f.origin}] {f.code} @ {label} {f.path}: {f.message}", file=sys.stderr)
        return 1

    print(
        f"[scientific-invariants] OK — {checked} projected object(s) passed the "
        f"vendored spine policy engine (no release-blocking code fired).",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout.",
    )
    args = parser.parse_args(argv)
    return run_gate(list(DEFAULT_CORPUS), emit_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
