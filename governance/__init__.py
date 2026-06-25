"""Track-B scientific-invariants governance layer for aop-mcp.

This package projects aop-mcp's RELEASED ``assess_aop_confidence.response`` object
onto canonical ToxMCP schema-spine shapes and runs the vendored, digest-pinned
spine policy engine over them via a fail-closed Node bridge. It is a *regression
tripwire* + proof-of-machinery: aop-mcp's confidence assessment is a DETERMINISTIC,
zero-LLM heuristic (``overall_call == heuristic_overall_call``; provenance
``phase1_oecd_alignment_normalization``) that natively issues an interpretive,
NON-causal, NON-regulatory conclusion. On the pristine corpus the gate is GREEN —
its job is to BLOCK if a future change ever lets a safety/zero-risk/regulatory
overclaim, a KER/causal mislabel of an AOP context anchor, or an uncapped
high-confidence call leak into a released assessment.

Anti-overclaim anchor: an AOP *confidence assessment* is NOT a regulatory
determination and an AOP context handoff is NOT KER truth or primary causal
evidence (see docs/adr/0002-trackb-scientific-invariants-gate.md). The projection
holds the released object at the spine ``association`` claim class and as an
``aop`` / ``context`` evidence anchor, never inflated to a high-stakes class the
producer does not assert.

Modules:
    errors           — the blocking-failure model + meta fail-closed codes.
    source_contract  — fail-closed PRODUCER emission-contract guard (runs FIRST).
    spine_bridge     — fail-closed Node shell-out to the vendored engine.
    project_to_spine — total, deterministic projection aop-mcp -> spine objects.
"""

from governance.errors import (
    SOURCE_CONTRACT_VIOLATION,
    BlockingFinding,
    ProjectionIncompleteError,
)
from governance.source_contract import validate_source_object

__all__ = [
    "BlockingFinding",
    "ProjectionIncompleteError",
    "SOURCE_CONTRACT_VIOLATION",
    "validate_source_object",
]
