"""Total native->spine projection for the aop-mcp Track-B scientific-invariants gate.

Maps the RELEASED aop-mcp ``assess_aop_confidence.response`` (an AOP *confidence
assessment*: a deterministic, zero-LLM heuristic over the AOP-Wiki RDF export) onto
canonical ToxMCP schema-spine shapes the vendored, digest-pinned policy engine
actually reasons about, using POSITIVE STRUCTURED / CANONICAL EVIDENCE drawn from
DECLARED producer fields ONLY. The projection is TOTAL: every required spine field is
populated from a declared source field or a structurally-faithful derivation; a field
that cannot be faithfully mapped raises ``ProjectionIncompleteError`` (a fail-closed
block), never a silent safe-default.

ANTI-OVERCLAIM POSTURE (the scientific anchor)
----------------------------------------------
An AOP confidence assessment is INTERPRETIVE MECHANISTIC CONTEXT, not a regulatory
determination and not a causal/KER establishment about any chemical. The producer
issues a four-rung heuristic call (``sparse_evidence`` / ``low`` / ``moderate`` /
``high``) over the *documented* evidence; it explicitly disclaims (in its own
``limitations`` narrative) that this is a determination. The projection therefore
holds the released object at the spine ``context_only`` claim class and as an
``aop`` / ``context`` evidence anchor with ``supportDirection == context_only`` —
never inflated to ``association`` / causal / risk / regulatory, postures the producer
does not assert.

WHAT IS PROJECTED, AND WHY THESE SHAPES
---------------------------------------
1. ``ClaimRecord`` (claimClass ``context_only``) — the interpretive claim the AOP
   confidence assessment carries. Its ``claimText`` is assembled from the producer's
   DECLARED narrative fields (the AOP ``title`` / ``abstract`` / ``evidence_summary``,
   the ``rationale[]`` and ``limitations[]`` arrays). These are the surfaces a future
   regression could let a safety / zero-risk / regulatory / causal overclaim slip into;
   the engine's anti-overclaim scanners — the ADVERTISED source-fault tripwires
   ``FREE_TEXT_OVERCLAIM``, ``ABSOLUTE_OR_REGULATORY_OVERCLAIM`` and
   ``CONTEXT_ONLY_OVERCLAIM`` — then BLOCK it. The claim's ``supportLevel`` is mapped
   FAITHFULLY from the producer's ``overall_call`` ladder, capped within the
   context_only band (never above weak); the downstream-use posture is fixed structural
   non-decision authorization.

2. ``EvidenceAnchor`` (evidenceClass ``aop``, role ``context``) — the AOP confidence
   assessment AS A CONTEXT HANDOFF. ``supportDirection`` is held at ``context_only``
   and ``targetEntity`` is the AOP identity (id/title); the engine's
   ``AOP_CONTEXT_NOT_KER_EVIDENCE`` invariant (the fourth ADVERTISED tripwire) BLOCKS
   if the handoff is ever re-labelled as KER truth or primary causal evidence — e.g.
   the producer-valid case where ker / causal language enters the DECLARED ``aop.title``
   and flows into the anchor's ``targetEntity``.

STRUCTURAL GUARDRAILS — ENFORCED BUT NOT ADVERTISED (documented in the ADR)
---------------------------------------------------------------------------
The context_only claim ALSO satisfies, on every faithful emission, three structural
invariants the engine still runs over the projected object:
``ONTOLOGY_CONFIDENCE_CEILING_EXCEEDED`` (support capped <= weak),
``CONTEXT_ONLY_BAD_DOWNSTREAM_USE`` and ``CONTEXT_ONLY_PROHIBITIONS_REQUIRED`` (the
allowed/prohibited downstream-use sets are FIXED structural posture, not derived from
any declared source field). Because NO producer-contract-valid SOURCE fault can drive
them through this faithful projection, they are deliberately NOT advertised as
source-fault tripwires (that would be an advertised-but-source-dead arm). They remain
ENFORCED — a projection regression that loosened the support cap or the downstream-use
sets would still fire them and BLOCK.

HONEST N/A (documented in the ADR)
----------------------------------
* AI-PROVENANCE arm: aop-mcp's confidence assessment is a DETERMINISTIC, zero-LLM
  heuristic (``overall_call == heuristic_overall_call``; provenance
  ``phase1_oecd_alignment_normalization``). The agent scaffold (``src/agent/
  workflows.py``) is a dry-run publish-plan orchestrator whose output never enters a
  released ``*.response`` object, and no released schema declares an
  AI/extraction/agent-provenance field. The gate therefore does NOT project an
  ``AssessmentRun`` and does NOT advertise any spine AI code; the deterministic N/A
  (and where the agent lane lives) is documented in the ADR.
* HIGH-CLAIM review codes (``HIGH_CLAIM_REQUIRES_REVIEW`` /
  ``HIGH_CLAIM_STRONG_SUPPORT_REQUIRES_REVIEW``) dispatch only on a HIGH-STAKES
  ``claimClass`` (causal_support / adversity / risk / regulatory_translation). The
  producer never asserts such a class, so projecting one would synthesize a posture no
  declared field carries (a dead arm). HONEST-DROPPED.

IDENTIFIER DISTINCTNESS
-----------------------
Where spine ids/refs are derived from declared identifier fields, they are folded
through an NFKD + Unicode-category (Mn/Cf) normalizer so a zero-width or combining
-diacritic decoration of an id cannot forge a spurious "distinct" reference.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from governance.errors import ProjectionIncompleteError

_SPINE = "https://schemas.ngra.ai/toxmcp"

CLAIM_RECORD_SCHEMA_ID = f"{_SPINE}/ClaimRecord.v1.schema.json"
EVIDENCE_ANCHOR_SCHEMA_ID = f"{_SPINE}/EvidenceAnchor.v1.schema.json"

# The producer's confidence ladder (verified against
# src/server/tools/aop.py::_build_overall_confidence_call).
_OVERALL_CALLS = frozenset({"sparse_evidence", "low", "moderate", "high"})

# Faithful mapping of the producer's confidence ladder onto the spine support level.
# The AOP confidence call is INTERPRETIVE CONTEXT, so it is mapped onto the
# context_only support band: a confidence assessment, however "high", never exceeds
# WEAK support for the released claim (it is not a decision-grade conclusion). This is
# the positive, structured re-grounding of the confidence-ceiling invariant — it is
# NOT inflation. If a future change tried to read "high" as moderate/strong support,
# ONTOLOGY_CONFIDENCE_CEILING_EXCEEDED would BLOCK it.
_OVERALL_CALL_TO_SUPPORT = {
    "sparse_evidence": "context_only",
    "low": "context_only",
    "moderate": "weak",
    "high": "weak",
}


def _normalize_identifier(value: str) -> str:
    """Fold an identifier to NFKD and strip combining marks (Mn) and format controls
    (Cf) so a zero-width / combining-diacritic decoration of an id cannot forge a
    spuriously "distinct" reference. Whitespace-trimmed and casefolded last so
    visually-identical ids collapse."""
    decomposed = unicodedata.normalize("NFKD", value)
    kept = [ch for ch in decomposed if unicodedata.category(ch) not in ("Mn", "Cf")]
    return "".join(kept).strip().casefold()


def _require(source: dict[str, Any], field: str, *, allowed: frozenset[str] | None = None) -> Any:
    if field not in source:
        raise ProjectionIncompleteError(
            f"assess_aop_confidence.response is missing required field {field!r}.",
            path=f"$.{field}",
        )
    value = source[field]
    if allowed is not None and value not in allowed:
        raise ProjectionIncompleteError(
            f"assess_aop_confidence.response.{field} value {value!r} is not a recognized "
            "producer enum.",
            path=f"$.{field}",
        )
    return value


def _str_list(source: dict[str, Any], field: str) -> list[str]:
    """A declared narrative array (rationale / limitations). Every item MUST be a
    string (the producer model emits list[str]); a non-string item is
    PROJECTION_INCOMPLETE rather than silently dropped."""
    value = _require(source, field)
    if not isinstance(value, list):
        raise ProjectionIncompleteError(
            f"assess_aop_confidence.response.{field} must be an array.", path=f"$.{field}"
        )
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise ProjectionIncompleteError(
                f"assess_aop_confidence.response.{field}[{idx}] must be a string.",
                path=f"$.{field}[{idx}]",
            )
        out.append(item)
    return out


def _aop_identity(source: dict[str, Any]) -> tuple[str, str, str]:
    """Return (aop_id, aop_title, aop_abstract) from the declared ``aop`` sub-object.
    The id is required (it is the assessment's subject); title/abstract default to
    empty strings when the AOP-Wiki export does not carry them."""
    aop = _require(source, "aop")
    if not isinstance(aop, dict):
        raise ProjectionIncompleteError("assess_aop_confidence.response.aop must be an object.", path="$.aop")
    aop_id = aop.get("id")
    if not isinstance(aop_id, str) or not aop_id.strip():
        raise ProjectionIncompleteError(
            "assess_aop_confidence.response.aop.id is required to identify the assessed AOP.",
            path="$.aop.id",
        )
    title = aop.get("title") if isinstance(aop.get("title"), str) else ""
    abstract = aop.get("abstract") if isinstance(aop.get("abstract"), str) else ""
    return aop_id, title, abstract


def _assemble_claim_text(source: dict[str, Any], aop_title: str, aop_abstract: str) -> str:
    """Assemble the interpretive claim's text from the producer's DECLARED narrative
    surfaces. Concatenating them here re-exposes any overclaim that slipped past the
    producer's own framing to the engine's anti-overclaim scanner. A summary with no
    narrative still yields a structural sentence so the claim text is never empty."""
    overall_call = _require(source, "overall_call", allowed=_OVERALL_CALLS)
    # IMPORTANT: the fixed prefix must NOT contain a NEGATED form of any overclaim
    # lexicon word (e.g. "does not establish causality", "is not safe"). The engine's
    # negation-aware scanner suppresses an overclaim phrase whenever a negation lead
    # abuts it ANYWHERE in the field, so a negated lexicon word in this prefix would
    # LAUNDER a genuine same-word overclaim appearing later in the declared narrative.
    # The prefix is therefore worded with no overclaim-lexicon token at all; the
    # non-determination posture is carried structurally by claimClass=context_only and
    # notARegulatoryConclusion=true, not by a narrative disclaimer.
    parts: list[str] = [
        "AOP confidence assessment (interpretive mechanistic context): overall heuristic "
        f"confidence call {overall_call.replace('_', ' ')}."
    ]
    if aop_title.strip():
        parts.append(aop_title.strip())
    if aop_abstract.strip():
        parts.append(aop_abstract.strip())
    aop = source.get("aop") or {}
    evidence_summary = aop.get("evidence_summary") if isinstance(aop, dict) else None
    if isinstance(evidence_summary, str) and evidence_summary.strip():
        parts.append(evidence_summary.strip())
    for line in _str_list(source, "rationale"):
        if line.strip():
            parts.append(line.strip())
    for line in _str_list(source, "limitations"):
        if line.strip():
            parts.append(line.strip())
    return " ".join(parts)


def project_claim_record(source: dict[str, Any], *, claim_id: str) -> dict[str, Any]:
    """Project the released assessment onto a spine ClaimRecord at the AOP confidence
    assessment's actual interpretive (``context_only``) class.

    Drives ``FREE_TEXT_OVERCLAIM`` / ``ABSOLUTE_OR_REGULATORY_OVERCLAIM`` /
    ``CONTEXT_ONLY_OVERCLAIM`` (from the declared narrative),
    ``ONTOLOGY_CONFIDENCE_CEILING_EXCEEDED`` (from the confidence-call -> support
    mapping), ``CONTEXT_ONLY_BAD_DOWNSTREAM_USE`` and
    ``CONTEXT_ONLY_PROHIBITIONS_REQUIRED`` (from the downstream-use authorization)."""
    overall_call = _require(source, "overall_call", allowed=_OVERALL_CALLS)
    aop_id, aop_title, aop_abstract = _aop_identity(source)
    support_level = _OVERALL_CALL_TO_SUPPORT[overall_call]
    base = _normalize_identifier(aop_id) or aop_id
    return {
        "schemaId": CLAIM_RECORD_SCHEMA_ID,
        "claimId": _normalize_identifier(claim_id) or claim_id,
        "claimText": _assemble_claim_text(source, aop_title, aop_abstract),
        # An AOP confidence assessment is interpretive context, NOT an association /
        # causal / risk / regulatory claim about any chemical. Held at context_only.
        "claimClass": "context_only",
        "endpoint": f"aop:{base}",
        "route": "not_applicable",
        "timeBasis": "not_assessed",
        "population": "not_assessed",
        "decisionContextRef": f"decision-context:aop:{base}",
        # Faithful confidence-ceiling mapping (never above weak for context_only).
        "supportLevel": support_level,
        "actionability": "requires_review",
        # The assessment authorizes ONLY non-decision, mechanistic-context uses.
        "allowedDownstreamUses": ["screening", "mechanistic_context"],
        # context_only claims MUST explicitly prohibit causal / KER / adversity /
        # risk / regulatory downstream claims (CONTEXT_ONLY_PROHIBITIONS_REQUIRED needs
        # one keyword from each group).
        "prohibitedDownstreamUses": [
            "causal_inference",
            "ker_establishment",
            "key event relationship establishment",
            "adversity_determination",
            "risk_assessment",
            "regulatory_submission",
        ],
        "requiredReviewState": "machine_checked",
        "notARegulatoryConclusion": True,
    }


def project_evidence_anchor(source: dict[str, Any], *, anchor_id: str, claim_ref: str) -> dict[str, Any]:
    """Project the released assessment onto a spine EvidenceAnchor as an AOP CONTEXT
    handoff. Drives ``AOP_CONTEXT_NOT_KER_EVIDENCE``: the AOP confidence assessment is
    context, never KER truth or primary causal evidence."""
    aop_id, aop_title, _ = _aop_identity(source)
    base = _normalize_identifier(aop_id) or aop_id
    # targetEntity is the AOP identity (id + title), which carries no ker/causal token
    # on a faithful emission. If a future change injected ker/causal language into the
    # AOP title, or flipped supportDirection off context_only, AOP_CONTEXT_NOT_KER_EVIDENCE
    # blocks.
    target_entity = f"AOP {aop_id}" + (f": {aop_title.strip()}" if aop_title.strip() else "")
    return {
        "schemaId": EVIDENCE_ANCHOR_SCHEMA_ID,
        "evidenceAnchorId": _normalize_identifier(anchor_id) or anchor_id,
        "claimRef": claim_ref,
        "evidenceClass": "aop",
        "role": "context",
        "supportDirection": "context_only",
        "targetEntity": target_entity,
        "limitations": _str_list(source, "limitations") or [
            "AOP confidence assessment is interpretive context, not KER or causal evidence."
        ],
        "sourceObjectRefs": [f"aop-confidence-assessment:{base}"],
    }


def project_assessment(
    source: dict[str, Any], *, object_label: str
) -> list[tuple[str, dict[str, Any]]]:
    """Total projection of one released assess_aop_confidence.response into spine
    objects. Returns ``[(label, spine_object), ...]``. Raises
    ``ProjectionIncompleteError`` (a fail-closed block) if any required field cannot be
    faithfully mapped."""
    aop_id, _, _ = _aop_identity(source)
    base = _normalize_identifier(aop_id) or aop_id
    claim_id = f"claim-aop-{base}"
    claim_ref = f"claim:{_normalize_identifier(claim_id) or claim_id}"
    return [
        (f"{object_label}#claim", project_claim_record(source, claim_id=claim_id)),
        (
            f"{object_label}#anchor",
            project_evidence_anchor(
                source, anchor_id=f"anchor-aop-{base}", claim_ref=claim_ref
            ),
        ),
    ]
