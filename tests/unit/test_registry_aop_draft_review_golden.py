from __future__ import annotations

import json

from tests.support.registry_aop_draft_review import (
    REGISTRY_AOP_DRAFT_PUBLICATION_GOLDEN,
    REGISTRY_AOP_DRAFT_REVIEW_ARTIFACTS_GOLDEN,
    REGISTRY_AOP_DRAFT_REVIEW_MARKDOWN_GOLDEN,
    build_registry_aop_draft_review_artifacts,
)


def test_registry_aop_draft_review_goldens_are_current() -> None:
    artifacts = build_registry_aop_draft_review_artifacts()
    structured_golden = json.loads(
        REGISTRY_AOP_DRAFT_REVIEW_ARTIFACTS_GOLDEN.read_text(encoding="utf-8")
    )

    assert structured_golden == {
        "review_bundle": artifacts["review_bundle"],
        "review_markdown_response": artifacts["review_markdown_response"],
        "publication_markdown_response": artifacts["publication_markdown_response"],
        "json_export_response": artifacts["json_export_response"],
        "json_export_content": artifacts["json_export_content"],
    }
    assert REGISTRY_AOP_DRAFT_REVIEW_MARKDOWN_GOLDEN.read_text(encoding="utf-8") == str(
        artifacts["review_markdown_content"]
    )
    assert REGISTRY_AOP_DRAFT_PUBLICATION_GOLDEN.read_text(encoding="utf-8") == str(
        artifacts["publication_markdown_content"]
    )

