from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.server.tools.aop import (
    ReviewRegistryHandoffBundleInput,
    review_registry_handoff_bundle,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "golden"
    / "cross_suite"
    / "registry_aop_context_handoff.v1.1.0.json"
)


@pytest.mark.asyncio
async def test_review_registry_handoff_bundle_preserves_bounded_use_caveats() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    result = await review_registry_handoff_bundle(
        ReviewRegistryHandoffBundleInput(bundle=payload)
    )

    assert result["source"]["target_consumer"] == "aop_context"
    assert result["summary"]["ready_for_aop_review"] is True
    assert result["summary"]["evidence_item_count"] == 2
    assert result["summary"]["not_comparable_applicability_count"] == 0
    assert any(
        "context_not_assay" in warning for warning in result["bounded_use_warnings"]
    )
    assert result["draft_import_plan"]["suggested_references"]
    assert any(
        "Manual KE/KER mapping is required"
        in action
        for action in result["draft_import_plan"]["required_manual_mapping"]
    )


@pytest.mark.asyncio
async def test_review_registry_handoff_bundle_rejects_wrong_target_consumer() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["targetConsumer"] = "woe_ngra"

    with pytest.raises(Exception):
        await review_registry_handoff_bundle(
            ReviewRegistryHandoffBundleInput(bundle=payload)
        )
