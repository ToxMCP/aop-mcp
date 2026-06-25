#!/usr/bin/env python3
"""Regenerate the Track-B pristine corpus fixture for the scientific-invariants gate.

Runs the REAL aop-mcp producer (``src/server/tools/aop.py::assess_aop_confidence``)
over a deterministic stub AOP-Wiki adapter, stamps the gate's ``objectType`` envelope
tag onto the authentic emission, and writes the fixture the gate's pristine corpus
loads. The emission is byte-for-byte what the producer serializes (the only added key
is the ``objectType`` discriminator the gate's corpus envelope requires; the strict
emission contract requires that exact ``const``).

This script imports the producer's own test stub adapter so the fixture stays a
FAITHFUL producer emission — never a hand-authored shape. Re-run after any producer
change that affects the assessment surface.

Usage:
    python scripts/build_spine_projection_goldens.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OBJECT_TYPE = "assess_aop_confidence.response"
OUTPUT = REPO_ROOT / "governance" / "fixtures" / "assess_aop_confidence.pristine.json"


def _build() -> dict:
    # Import inside the function so the heavy server deps load only when generating.
    import src.server.tools.aop as aop_tools
    from src.server.tools.aop import assess_aop_confidence, AssessAopConfidenceInput
    from tests.unit.test_aop_oecd_tools import StubWikiAdapter

    original = aop_tools.get_aop_wiki_adapter
    aop_tools.get_aop_wiki_adapter = lambda: StubWikiAdapter()
    try:
        result = asyncio.run(
            assess_aop_confidence(AssessAopConfidenceInput(aop_id="AOP:232"))
        )
    finally:
        aop_tools.get_aop_wiki_adapter = original

    # The gate's corpus envelope tag — the only key added to the authentic emission.
    return {"objectType": OBJECT_TYPE, **result}


def main() -> int:
    payload = _build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[build-goldens] wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
