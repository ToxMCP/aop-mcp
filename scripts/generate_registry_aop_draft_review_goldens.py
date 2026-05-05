from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.support.registry_aop_draft_review import (
    REGISTRY_AOP_DRAFT_PUBLICATION_GOLDEN,
    REGISTRY_AOP_DRAFT_REVIEW_ARTIFACTS_GOLDEN,
    REGISTRY_AOP_DRAFT_REVIEW_MARKDOWN_GOLDEN,
    build_registry_aop_draft_review_artifacts,
)


def main() -> None:
    artifacts = build_registry_aop_draft_review_artifacts()
    REGISTRY_AOP_DRAFT_REVIEW_ARTIFACTS_GOLDEN.write_text(
        json.dumps(
            {
                "review_bundle": artifacts["review_bundle"],
                "review_markdown_response": artifacts["review_markdown_response"],
                "publication_markdown_response": artifacts["publication_markdown_response"],
                "json_export_response": artifacts["json_export_response"],
                "json_export_content": artifacts["json_export_content"],
            },
            indent=2,
            sort_keys=False,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    REGISTRY_AOP_DRAFT_REVIEW_MARKDOWN_GOLDEN.write_text(
        str(artifacts["review_markdown_content"]),
        encoding="utf-8",
    )
    REGISTRY_AOP_DRAFT_PUBLICATION_GOLDEN.write_text(
        str(artifacts["publication_markdown_content"]),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
