from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from src.server.tools import aop as aop_tools
from src.services.draft_store import DraftStoreService, InMemoryDraftRepository
from src.tools.write import WriteTools


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_AOP_HANDOFF_FIXTURE = (
    REPO_ROOT / "tests" / "golden" / "cross_suite" / "registry_aop_context_handoff.v1.1.0.json"
)
REGISTRY_AOP_DRAFT_REVIEW_ARTIFACTS_GOLDEN = (
    REPO_ROOT / "tests" / "golden" / "cross_suite" / "registry_aop_draft_review_artifacts.v1.json"
)
REGISTRY_AOP_DRAFT_REVIEW_MARKDOWN_GOLDEN = (
    REPO_ROOT / "tests" / "golden" / "cross_suite" / "registry_aop_draft_review_export.review.md"
)
REGISTRY_AOP_DRAFT_PUBLICATION_GOLDEN = (
    REPO_ROOT / "tests" / "golden" / "cross_suite" / "registry_aop_draft_review_export.publication.md"
)


class RegistryDraftReviewDbAdapter:
    async def search_assays_for_key_event(
        self,
        key_event: dict[str, object],
        *,
        limit: int = 25,
    ) -> dict[str, object]:
        key_event_id = str(key_event.get("id") or "")
        title = str(key_event.get("title") or "")
        if key_event_id == "KE:1":
            return {
                "derived_search_terms": {
                    "gene_symbols": ["NR1I2", "PXR"],
                    "phrases": ["pregnane x receptor activation"],
                },
                "limitations": [
                    "Assays are ranked by key-event-derived gene and phrase matches in the CompTox assay catalog; this is not a curated KE-to-assay ontology mapping."
                ],
                "results": [
                    {
                        "aeid": 103,
                        "assay_name": "ATG_PXRE_CIS",
                        "gene_symbols": ["NR1I2"],
                        "match_score": 245,
                        "match_basis": ["gene_symbol_exact"],
                        "matched_terms": ["NR1I2"],
                        "specificity_score": 0.92,
                        "source": "comptox_assay_catalog",
                    }
                ][:limit],
            }
        return {
            "derived_search_terms": {
                "gene_symbols": [],
                "phrases": [title.lower()] if title else [],
            },
            "limitations": [
                "Assays are ranked by key-event-derived gene and phrase matches in the CompTox assay catalog; this is not a curated KE-to-assay ontology mapping."
            ],
            "results": [],
        }


async def _build_registry_aop_draft_review_artifacts_async() -> dict[str, object]:
    handoff_bundle = json.loads(REGISTRY_AOP_HANDOFF_FIXTURE.read_text(encoding="utf-8"))
    draft_store = DraftStoreService(InMemoryDraftRepository())
    write_tools = WriteTools(draft_service=draft_store)

    with (
        patch.object(aop_tools, "get_draft_store", return_value=draft_store),
        patch.object(aop_tools, "get_write_tools", return_value=write_tools),
        patch.object(aop_tools, "get_aop_db_adapter", return_value=RegistryDraftReviewDbAdapter()),
    ):
        await aop_tools.create_draft_aop(
            aop_tools.CreateDraftInputModel(
                draft_id="draft-registry-aop-golden",
                title="Registry-supported mechanistic context review",
                description="Deterministic cross-suite draft review fixture with imported Registry support.",
                adverse_outcome="Liver steatosis",
                author="fixture-generator",
                summary="create deterministic golden draft",
            )
        )
        await aop_tools.attach_registry_handoff_to_draft(
            aop_tools.AttachRegistryHandoffToDraftInputModel(
                draft_id="draft-registry-aop-golden",
                version_id="v2",
                author="fixture-generator",
                summary="attach registry aop_context support",
                bundle=handoff_bundle,
            )
        )
        await aop_tools.add_or_update_ke(
            aop_tools.KeyEventInputModel(
                draft_id="draft-registry-aop-golden",
                version_id="v3",
                author="fixture-generator",
                summary="add mechanistic initiating event",
                identifier="KE:1",
                title="Activation, Pregnane-X receptor, NR1I2",
                event_role="mie",
                attributes={
                    "measurement_methods": ["Reporter assay"],
                    "taxonomic_applicability": ["NCBITaxon:9606"],
                },
            )
        )
        await aop_tools.add_or_update_ke(
            aop_tools.KeyEventInputModel(
                draft_id="draft-registry-aop-golden",
                version_id="v4",
                author="fixture-generator",
                summary="add adverse outcome",
                identifier="KE:2",
                title="Liver steatosis",
                event_role="ao",
                attributes={"measurement": "Histopathology"},
            )
        )
        await aop_tools.add_or_update_ker(
            aop_tools.KerInputModel(
                draft_id="draft-registry-aop-golden",
                version_id="v5",
                author="fixture-generator",
                summary="add mechanistic relationship",
                identifier="KER:1",
                upstream="KE:1",
                downstream="KE:2",
                plausibility="Mechanistic support remains bounded and contextual.",
            )
        )

        review_bundle = await aop_tools.review_draft_bundle(
            aop_tools.ReviewDraftBundleInput(
                draft_id="draft-registry-aop-golden",
                assay_limit=3,
                stressor_limit=5,
                min_hitcall=0.9,
            )
        )
        review_markdown = await aop_tools.export_draft_review_artifact(
            aop_tools.ExportDraftReviewArtifactInput(
                draft_id="draft-registry-aop-golden",
                format="markdown",
                artifact_profile="review",
                assay_limit=3,
                stressor_limit=5,
                min_hitcall=0.9,
            )
        )
        publication_markdown = await aop_tools.export_draft_review_artifact(
            aop_tools.ExportDraftReviewArtifactInput(
                draft_id="draft-registry-aop-golden",
                format="markdown",
                artifact_profile="publication",
                assay_limit=3,
                stressor_limit=5,
                min_hitcall=0.9,
            )
        )
        json_export = await aop_tools.export_draft_review_artifact(
            aop_tools.ExportDraftReviewArtifactInput(
                draft_id="draft-registry-aop-golden",
                format="json",
                artifact_profile="review",
                assay_limit=3,
                stressor_limit=5,
                min_hitcall=0.9,
            )
        )

    return {
        "review_bundle": review_bundle,
        "review_markdown_response": {
            key: value for key, value in review_markdown.items() if key != "content"
        },
        "review_markdown_content": review_markdown["content"],
        "publication_markdown_response": {
            key: value
            for key, value in publication_markdown.items()
            if key != "content"
        },
        "publication_markdown_content": publication_markdown["content"],
        "json_export_response": {
            key: value for key, value in json_export.items() if key != "content"
        },
        "json_export_content": json.loads(json_export["content"]),
    }


def build_registry_aop_draft_review_artifacts() -> dict[str, object]:
    return asyncio.run(_build_registry_aop_draft_review_artifacts_async())

