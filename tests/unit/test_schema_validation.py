from __future__ import annotations

import pytest

from src.adapters import AOPWikiAdapter, AOPDBAdapter, SparqlClient
from src.tools import SchemaValidationError, validate_payload

import httpx


def make_client(response_json: dict) -> SparqlClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    transport = httpx.MockTransport(handler)
    return SparqlClient(["https://sparql.example"], transport=transport)


@pytest.mark.asyncio
async def test_search_aops_schema_validation() -> None:
    payload = {
        "results": {
            "bindings": [
                {
                    "aop": {"value": "http://aopwiki.org/aops/1"},
                    "title": {"value": "Example"},
                    "shortName": {"value": "AOP1"},
                }
            ]
        }
    }

    async with make_client(payload) as client:
        adapter = AOPWikiAdapter(client, cache_ttl_seconds=0)
        results = await adapter.search_aops()

    validate_payload({"results": results}, namespace="read", name="search_aops.response.schema")


@pytest.mark.asyncio
async def test_map_chemical_to_aops_schema_validation() -> None:
    response_json = {
        "results": {
            "bindings": [
                {
                    "aop": {"value": "http://aopwiki.org/aops/25"},
                    "title": {"value": "Example"},
                    "stressId": {"value": "DSS:123"},
                }
            ]
        }
    }

    async with make_client(response_json) as client:
        adapter = AOPDBAdapter(client, cache_ttl_seconds=0)
        results = await adapter.map_chemical_to_aops(name="example")

    validate_payload({"results": results}, namespace="read", name="map_chemical_to_aops.response.schema")


@pytest.mark.asyncio
async def test_map_assay_to_aops_schema_validation() -> None:
    response_json = {
        "results": {
            "bindings": [
                {
                    "aop": {"value": "http://aopwiki.org/aops/25"},
                    "title": {"value": "Example"},
                }
            ]
        }
    }

    async with make_client(response_json) as client:
        adapter = AOPDBAdapter(client, cache_ttl_seconds=0, comptox_client=None)
        results = await adapter.map_assay_to_aops("HTS123")

    validate_payload({"results": results}, namespace="read", name="map_assay_to_aops.response.schema")


def test_list_assays_for_aop_schema_validation_with_diagnostics() -> None:
    payload = {
        "results": [],
        "diagnostics": {
            "aop_id": "AOP:529",
            "comptox_api_key_configured": False,
            "stressor_count": 0,
            "chemical_match_count": 0,
            "bioactivity_hit_count": 0,
            "returned_assay_count": 0,
            "empty_reason": "missing_comptox_api_key",
            "warnings": ["CompTox API key is not configured."],
        },
    }

    validate_payload(payload, namespace="read", name="list_assays_for_aop.response.schema")


def test_list_assays_for_aops_schema_validation_with_diagnostics() -> None:
    payload = {
        "results": [],
        "diagnostics": {
            "requested_aop_ids": ["AOP:529", "AOP:591"],
            "processed_aop_ids": ["AOP:529", "AOP:591"],
            "returned_assay_count": 0,
            "per_aop": [
                {
                    "aop_id": "AOP:529",
                    "comptox_api_key_configured": True,
                    "stressor_count": 1,
                    "chemical_match_count": 0,
                    "bioactivity_hit_count": 0,
                    "returned_assay_count": 0,
                    "empty_reason": "no_comptox_chemical_match",
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }

    validate_payload(payload, namespace="read", name="list_assays_for_aops.response.schema")


def test_list_assays_for_query_schema_validation_with_diagnostics() -> None:
    payload = {
        "query": "liver steatosis",
        "selected_aops": [{"id": "AOP:529", "title": "PPAR steatosis"}],
        "results": [],
        "diagnostics": {
            "query": "liver steatosis",
            "matched_aop_count": 3,
            "selected_aop_count": 1,
            "returned_assay_count": 0,
            "per_aop": [
                {
                    "aop_id": "AOP:529",
                    "comptox_api_key_configured": True,
                    "stressor_count": 1,
                    "chemical_match_count": 1,
                    "bioactivity_hit_count": 0,
                    "returned_assay_count": 0,
                    "empty_reason": "no_bioactivity_hits_after_filtering",
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }

    validate_payload(payload, namespace="read", name="list_assays_for_query.response.schema")


def test_discover_orphan_stressors_for_aop_schema_validation_with_diagnostics() -> None:
    payload = {
        "results": [
            {
                "dtxsid": "DTXSID0000001",
                "casrn": "111-11-1",
                "preferred_name": "Alpha candidate",
                "supporting_assay_count": 2,
                "best_assay_rank": 1,
                "max_specificity_score": 0.8,
                "supporting_assays": [
                    {
                        "aeid": 103,
                        "assay_name": "ATG_PXRE_CIS",
                        "rank": 1,
                        "specificity_score": 0.8,
                    }
                ],
            }
        ],
        "diagnostics": {
            "aop_id": "AOP:529",
            "comptox_api_key_configured": True,
            "curated_stressor_count": 1,
            "curated_chemical_match_count": 1,
            "assay_candidate_count": 2,
            "scanned_assay_count": 2,
            "assay_chemical_hit_count": 5,
            "returned_candidate_count": 1,
            "empty_reason": None,
            "warnings": [],
        },
    }

    validate_payload(
        payload,
        namespace="read",
        name="discover_orphan_stressors_for_aop.response.schema",
    )


def test_discover_orphan_stressors_for_aops_schema_validation_with_diagnostics() -> None:
    payload = {
        "results": [
            {
                "dtxsid": "DTXSID0000001",
                "casrn": "111-11-1",
                "preferred_name": "Alpha candidate",
                "aop_support_count": 2,
                "supporting_aops": ["AOP:529", "AOP:591"],
                "supporting_assay_count": 3,
                "best_assay_rank": 1,
                "max_specificity_score": 0.8,
                "supporting_assays": [
                    {
                        "aop_id": "AOP:529",
                        "aeid": 103,
                        "assay_name": "ATG_PXRE_CIS",
                        "rank": 1,
                        "specificity_score": 0.8,
                    }
                ],
            }
        ],
        "diagnostics": {
            "requested_aop_ids": ["AOP:529", "AOP:591"],
            "processed_aop_ids": ["AOP:529", "AOP:591"],
            "returned_candidate_count": 1,
            "per_aop": [
                {
                    "aop_id": "AOP:529",
                    "comptox_api_key_configured": True,
                    "curated_stressor_count": 1,
                    "curated_chemical_match_count": 1,
                    "assay_candidate_count": 2,
                    "scanned_assay_count": 2,
                    "assay_chemical_hit_count": 5,
                    "returned_candidate_count": 1,
                    "empty_reason": None,
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }

    validate_payload(
        payload,
        namespace="read",
        name="discover_orphan_stressors_for_aops.response.schema",
    )


def test_discover_orphan_stressors_for_query_schema_validation_with_diagnostics() -> None:
    payload = {
        "query": "liver steatosis",
        "selected_aops": [{"id": "AOP:529", "title": "PPAR steatosis"}],
        "results": [
            {
                "dtxsid": "DTXSID0000001",
                "casrn": "111-11-1",
                "preferred_name": "Alpha candidate",
                "aop_support_count": 2,
                "supporting_aops": ["AOP:529", "AOP:591"],
                "supporting_assay_count": 3,
                "best_assay_rank": 1,
                "max_specificity_score": 0.8,
                "supporting_assays": [
                    {
                        "aop_id": "AOP:529",
                        "aeid": 103,
                        "assay_name": "ATG_PXRE_CIS",
                        "rank": 1,
                        "specificity_score": 0.8,
                    }
                ],
            }
        ],
        "diagnostics": {
            "query": "liver steatosis",
            "matched_aop_count": 3,
            "selected_aop_count": 1,
            "returned_candidate_count": 1,
            "per_aop": [
                {
                    "aop_id": "AOP:529",
                    "comptox_api_key_configured": True,
                    "curated_stressor_count": 1,
                    "curated_chemical_match_count": 1,
                    "assay_candidate_count": 2,
                    "scanned_assay_count": 2,
                    "assay_chemical_hit_count": 5,
                    "returned_candidate_count": 1,
                    "empty_reason": None,
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
    }

    validate_payload(
        payload,
        namespace="read",
        name="discover_orphan_stressors_for_query.response.schema",
    )


def test_review_draft_assay_cutoff_ordering_schema_validation() -> None:
    payload = {
        "draft_id": "draft-1",
        "version_id": "v5",
        "draft": {
            "aop_entity_id": "AOP:draft-1",
            "title": "PXR activation leading to liver steatosis",
            "adverse_outcome": "Liver steatosis",
        },
        "review_parameters": {
            "assay_limit": 5,
            "stressor_limit": 10,
            "min_hitcall": 0.9,
        },
        "summary": {
            "key_event_count": 2,
            "relationship_count": 1,
            "linked_stressor_count": 1,
            "scanned_stressor_count": 1,
            "searchable_stressor_count": 1,
            "assessable_relationship_count": 1,
            "concordant_relationship_count": 1,
            "discordant_relationship_count": 0,
            "not_reported_relationship_count": 0,
            "supporting_chemical_count": 1,
        },
        "stressors": [
            {
                "stressor_id": "CHEM:PFOS",
                "label": "Perfluorooctanesulfonic acid",
                "source": "1763-23-1",
                "casrn": "1763-23-1",
                "dtxsid": None,
                "linked_target_ids": ["KE:1"],
                "searchable": True,
            }
        ],
        "key_events": [
            {
                "id": "KE:1",
                "title": "Activation, Pregnane-X receptor, NR1I2",
                "event_type": None,
                "event_role": "mie",
            },
            {
                "id": "KE:2",
                "title": "Liver steatosis",
                "event_type": None,
                "event_role": "ao",
            },
        ],
        "relationships": [
            {
                "id": "KER:1",
                "source": "KE:1",
                "target": "KE:2",
                "type": "KeyEventRelationship",
                "plausibility": "Strong mechanistic rationale.",
                "status": None,
                "assay_cutoff_ordering_call": "moderate",
                "assay_cutoff_supporting_chemical_count": 1,
                "assay_cutoff_ordering": {
                    "heuristic_call": "moderate",
                    "basis": "All 1 shared linked-stressor chemical comparison showed upstream assay cutoffs less than or equal to downstream assay cutoffs. This is a supplemental quantitative-ordering heuristic derived from KE assay discovery plus linked-stressor bioactivity.",
                    "upstream_candidate_assay_count": 1,
                    "downstream_candidate_assay_count": 1,
                    "supporting_chemical_count": 1,
                    "concordant_chemical_count": 1,
                    "discordant_chemical_count": 0,
                    "supporting_chemicals": [
                        {
                            "dtxsid": "DTXSID3031864",
                            "preferred_name": "Perfluorooctanesulfonic acid",
                            "casrn": "1763-23-1",
                            "upstream_best_activity_cutoff": 12.0,
                            "downstream_best_activity_cutoff": 28.0,
                            "ordering": "concordant",
                        }
                    ],
                    "provenance": [
                        {
                            "source": "derived_from_ke_assays_and_comptox_bioactivity",
                            "field": "assay_cutoff_ordering",
                            "transformation": "phase4_assay_cutoff_ordering_concordant",
                            "confidence": "low",
                        }
                    ],
                },
            }
        ],
        "limitations": [],
    }

    validate_payload(
        payload,
        namespace="read",
        name="review_draft_assay_cutoff_ordering.response.schema",
    )


def test_review_draft_bundle_schema_validation() -> None:
    payload = {
        "draft_id": "draft-1",
        "version_id": "v5",
        "draft": {
            "aop_entity_id": "AOP:draft-1",
            "title": "PXR activation leading to liver steatosis",
            "adverse_outcome": "Liver steatosis",
        },
        "review_parameters": {
            "assay_limit": 5,
            "stressor_limit": 10,
            "min_hitcall": 0.9,
            "chemical_trace_requested": False,
        },
        "chemical_query": {
            "dtxsid": None,
            "cas": None,
            "inchikey": None,
            "name": None,
        },
        "bundle_summary": {
            "ready_for_review": True,
            "validator_error_count": 0,
            "validator_warning_count": 2,
            "assay_cutoff_assessable_relationship_count": 1,
            "assay_cutoff_discordant_relationship_count": 0,
            "chemical_trace_included": False,
            "traced_key_event_count": 0,
            "active_key_event_count": 0,
            "total_gap_count": 2,
            "blocking_gap_count": 1,
            "advisory_gap_count": 1,
        },
        "evidence_gap_summary": {
            "ready_for_review": True,
            "total_gap_count": 2,
            "blocking_gap_count": 1,
            "advisory_gap_count": 1,
            "global_gap_count": 1,
            "key_event_gap_count": 1,
            "relationship_gap_count": 0,
            "stressor_gap_count": 0,
            "assay_mapping_gap_count": 1,
        },
        "validation": {
            "draft_id": "draft-1",
            "version_id": "v5",
            "summary": {
                "error_count": 0,
                "warning_count": 2,
                "ready_for_review": True,
                "score": 90,
            },
            "results": [
                {
                    "id": "ke_essentiality_coverage",
                    "label": "Key events include explicit essentiality status",
                    "status": "fail",
                    "severity": "warning",
                    "message": "0/2 key events include governed essentiality metadata.",
                }
            ],
        },
        "quantitative_review": {
            "draft_id": "draft-1",
            "version_id": "v5",
            "draft": {
                "aop_entity_id": "AOP:draft-1",
                "title": "PXR activation leading to liver steatosis",
                "adverse_outcome": "Liver steatosis",
            },
            "review_parameters": {
                "assay_limit": 5,
                "stressor_limit": 10,
                "min_hitcall": 0.9,
            },
            "summary": {
                "key_event_count": 2,
                "relationship_count": 1,
                "linked_stressor_count": 1,
                "scanned_stressor_count": 1,
                "searchable_stressor_count": 1,
                "assessable_relationship_count": 1,
                "concordant_relationship_count": 1,
                "discordant_relationship_count": 0,
                "not_reported_relationship_count": 0,
                "supporting_chemical_count": 1,
            },
            "stressors": [],
            "key_events": [],
            "relationships": [],
            "limitations": [],
        },
        "chemical_trace": None,
        "external_support": {
            "summary": {
                "attached_bundle_count": 0,
                "ready_bundle_count": 0,
                "total_evidence_item_count": 0,
                "total_bounded_use_warning_count": 0,
                "total_scientific_review_flag_count": 0,
                "blocking_issue_count": 0,
                "advisory_issue_count": 0,
            },
            "imports": [],
            "limitations": [],
        },
        "evidence_gaps": {
            "draft_id": "draft-1",
            "version_id": "v5",
            "draft": {
                "aop_entity_id": "AOP:draft-1",
                "title": "PXR activation leading to liver steatosis",
                "adverse_outcome": "Liver steatosis",
            },
            "review_parameters": {
                "assay_limit": 5,
                "stressor_limit": 10,
                "min_hitcall": 0.9,
            },
            "bundle_summary": {
                "ready_for_review": True,
                "validator_error_count": 0,
                "validator_warning_count": 2,
                "assay_cutoff_assessable_relationship_count": 1,
                "assay_cutoff_discordant_relationship_count": 0,
                "chemical_trace_included": False,
                "traced_key_event_count": 0,
                "active_key_event_count": 0,
            },
            "summary": {
                "ready_for_review": True,
                "total_gap_count": 2,
                "blocking_gap_count": 1,
                "advisory_gap_count": 1,
                "global_gap_count": 1,
                "key_event_gap_count": 1,
                "relationship_gap_count": 0,
                "stressor_gap_count": 0,
                "assay_mapping_gap_count": 1,
            },
            "global_gaps": [
                {
                    "id": "draft_root_metadata_missing",
                    "severity": "error",
                    "title": "Draft root metadata is incomplete",
                    "detail": "Provide root metadata.",
                }
            ],
            "key_events": [
                {
                    "id": "KE:1",
                    "title": "PXR activation",
                    "candidate_assay_count": 0,
                    "gaps": [
                        {
                            "id": "ke_assay_mapping_missing",
                            "severity": "warning",
                            "title": "No assay mapping",
                            "detail": "Add measurement guidance.",
                        }
                    ],
                }
            ],
            "relationships": [],
            "stressors": [],
            "recommendations": ["Add measurement guidance to KE:1."],
            "limitations": [],
        },
        "limitations": [
            "0/2 key events include governed essentiality metadata.",
            "Chemical trace was not included because no chemical identifier was supplied.",
        ],
    }

    validate_payload(
        payload,
        namespace="read",
        name="review_draft_bundle.response.schema",
    )


def test_export_draft_review_artifact_schema_validation() -> None:
    payload = {
        "format": "markdown",
        "artifact_profile": "review",
        "filename": "draft_review_draft_1.md",
        "draft_id": "draft-1",
        "version_id": "v5",
        "bundle_summary": {
            "ready_for_review": True,
            "validator_error_count": 0,
            "validator_warning_count": 2,
            "assay_cutoff_assessable_relationship_count": 1,
            "assay_cutoff_discordant_relationship_count": 0,
            "chemical_trace_included": False,
            "traced_key_event_count": 0,
            "active_key_event_count": 0,
            "total_gap_count": 3,
            "blocking_gap_count": 0,
            "advisory_gap_count": 3,
        },
        "evidence_gap_summary": {
            "ready_for_review": True,
            "total_gap_count": 3,
            "blocking_gap_count": 0,
            "advisory_gap_count": 3,
            "global_gap_count": 1,
            "key_event_gap_count": 1,
            "relationship_gap_count": 1,
            "stressor_gap_count": 0,
            "assay_mapping_gap_count": 0,
        },
        "section_titles": [
            "Draft Review Summary",
            "Validation Findings",
            "Quantitative Review",
            "Chemical Trace",
            "Evidence Gaps",
            "External Support",
            "Recommended Next Actions",
            "Limitations"
        ],
        "content": "# Draft Review Artifact: Example\n"
    }

    validate_payload(
        payload,
        namespace="read",
        name="export_draft_review_artifact.response.schema",
    )


def test_save_draft_review_artifact_schema_validation() -> None:
    payload = {
        "format": "markdown",
        "artifact_profile": "publication",
        "draft_id": "draft-1",
        "version_id": "v5",
        "filename": "scientist_review.md",
        "path": "/tmp/output/draft_reviews/scientist_review.md",
        "relative_path": "scientist_review.md",
        "metadata_path": "/tmp/output/draft_reviews/scientist_review.md.meta.json",
        "output_directory": "/tmp/output/draft_reviews",
        "bundle_summary": {
            "ready_for_review": True,
            "validator_error_count": 0,
            "validator_warning_count": 2,
            "assay_cutoff_assessable_relationship_count": 1,
            "assay_cutoff_discordant_relationship_count": 0,
            "chemical_trace_included": False,
            "traced_key_event_count": 0,
            "active_key_event_count": 0,
            "total_gap_count": 3,
            "blocking_gap_count": 0,
            "advisory_gap_count": 3,
        },
        "evidence_gap_summary": {
            "ready_for_review": True,
            "total_gap_count": 3,
            "blocking_gap_count": 0,
            "advisory_gap_count": 3,
            "global_gap_count": 1,
            "key_event_gap_count": 1,
            "relationship_gap_count": 1,
            "stressor_gap_count": 0,
            "assay_mapping_gap_count": 0,
        },
        "section_titles": [
            "Executive Summary",
            "Draft Context",
            "Review Findings",
            "Quantitative Evidence",
            "Evidence Gaps",
            "Chemical Activity Overlay",
            "External Support",
            "Recommended Next Actions",
            "Limitations and Interpretation"
        ],
        "bytes_written": 2048,
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "artifact_integrity": {
            "algorithm": "sha256-v1",
            "content_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "metadata_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        },
        "draft_version_integrity": {
            "checksum_algorithm": "sha256-v1",
            "graph_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
            "previous_graph_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
            "provenance_checksum_algorithm": "sha256-v1",
            "provenance_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
        },
        "saved_at": "2026-04-12T12:00:00Z",
        "overwrote_existing_file": False,
    }

    validate_payload(
        payload,
        namespace="write",
        name="save_draft_review_artifact.response.schema",
    )


def test_list_saved_draft_review_artifacts_schema_validation() -> None:
    payload = {
        "results": [
            {
                "filename": "scientist_review.md",
                "path": "/tmp/output/draft_reviews/handoff/scientist_review.md",
                "relative_path": "handoff/scientist_review.md",
                "output_directory": "/tmp/output/draft_reviews/handoff",
                "format": "markdown",
                "artifact_profile": "publication",
                "draft_id": "draft-1",
                "version_id": "v5",
                "bytes_written": 2048,
                "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "artifact_integrity": {
                    "algorithm": "sha256-v1",
                    "content_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "metadata_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
                },
                "draft_version_integrity": {
                    "checksum_algorithm": "sha256-v1",
                    "graph_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
                    "previous_graph_sha256": "",
                    "provenance_checksum_algorithm": "sha256-v1",
                    "provenance_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
                },
                "integrity_check": {
                    "overall_status": "verified",
                    "content_status": "verified",
                    "metadata_status": "verified",
                    "content_sha256_actual": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "content_sha256_expected": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "metadata_sha256_actual": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
                    "metadata_sha256_expected": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
                    "messages": [],
                },
                "saved_at": "2026-04-12T12:00:00Z",
                "metadata_available": True,
                "metadata_path": "/tmp/output/draft_reviews/handoff/scientist_review.md.meta.json",
                "bundle_summary": {
                    "ready_for_review": True,
                    "validator_error_count": 0,
                    "validator_warning_count": 2,
                    "assay_cutoff_assessable_relationship_count": 1,
                    "assay_cutoff_discordant_relationship_count": 0,
                    "chemical_trace_included": False,
                    "traced_key_event_count": 0,
                    "active_key_event_count": 0,
                    "total_gap_count": 3,
                    "blocking_gap_count": 0,
                    "advisory_gap_count": 3,
                },
                "evidence_gap_summary": {
                    "ready_for_review": True,
                    "total_gap_count": 3,
                    "blocking_gap_count": 0,
                    "advisory_gap_count": 3,
                    "global_gap_count": 1,
                    "key_event_gap_count": 1,
                    "relationship_gap_count": 1,
                    "stressor_gap_count": 0,
                    "assay_mapping_gap_count": 0,
                }
            }
        ],
        "diagnostics": {
            "artifact_root_directory": "/tmp/output/draft_reviews",
            "scanned_directory": "/tmp/output/draft_reviews/handoff",
            "scanned_artifact_count": 1,
            "returned_artifact_count": 1,
            "missing_metadata_count": 0,
            "warnings": []
        }
    }

    validate_payload(
        payload,
        namespace="read",
        name="list_saved_draft_review_artifacts.response.schema",
    )


def test_export_draft_replay_package_schema_validation() -> None:
    payload = {
        "package_schema_version": "draft-replay-package.v1",
        "generated_at": "2026-04-12T12:00:00Z",
        "draft_id": "draft-1",
        "version_id": "v1",
        "draft_snapshot": {
            "draft": {
                "draft_id": "draft-1",
                "title": "Example draft",
                "status": "draft",
                "created_at": "2026-04-12T12:00:00Z",
                "updated_at": "2026-04-12T12:00:00Z",
                "tags": [],
                "version_count": 1,
            },
            "version": {
                "version_id": "v1",
                "author": "tester",
                "summary": "create draft",
                "created_at": "2026-04-12T12:00:00Z",
                "provenance": {},
                "checksum": "1111111111111111111111111111111111111111111111111111111111111111",
                "previous_checksum": "",
                "checksum_algorithm": "sha256-v1",
                "provenance_checksum": "2222222222222222222222222222222222222222222222222222222222222222",
                "provenance_checksum_algorithm": "sha256-v1",
                "signatures": [],
            },
            "graph": {
                "entity_count": 1,
                "relationship_count": 0,
                "entities": [
                    {
                        "identifier": "AOP:draft-1",
                        "type": "AdverseOutcomePathway",
                        "attributes": {"title": "Example draft"},
                    }
                ],
                "relationships": [],
            },
            "diff_summary": {
                "added_entity_count": 1,
                "removed_entity_count": 0,
                "updated_entity_count": 0,
                "added_relationship_count": 0,
                "removed_relationship_count": 0,
                "updated_relationship_count": 0,
            },
        },
        "draft_integrity": {
            "audit_chain": True,
            "provenance": True,
            "overall": True,
            "selected_version": {
                "checksum_algorithm": "sha256-v1",
                "graph_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
                "previous_graph_sha256": "",
                "provenance_checksum_algorithm": "sha256-v1",
                "provenance_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
            },
        },
        "external_support": {
            "summary": {
                "attached_bundle_count": 0,
                "ready_bundle_count": 0,
                "total_evidence_item_count": 0,
                "total_bounded_use_warning_count": 0,
                "total_scientific_review_flag_count": 0,
                "blocking_issue_count": 0,
                "advisory_issue_count": 0,
            },
            "imports": [],
            "limitations": [],
        },
        "saved_artifact": None,
        "audit_records": {
            "scope": "process_local_recent_records",
            "included": False,
            "limit": 0,
            "included_record_count": 0,
            "records": [],
        },
        "limitations": [
            "Replay package audit records are drawn from the process-local MCP audit buffer and may not include historical calls from prior server runs.",
            "Replay package verifies stored checksums but does not provide an immutable ledger or third-party timestamp.",
        ],
        "package_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
    }

    validate_payload(
        payload,
        namespace="read",
        name="export_draft_replay_package.response.schema",
    )


def test_plan_linear_draft_review_document_schema_validation() -> None:
    payload = {
        "source": {
            "mode": "saved_artifact",
            "draft_id": "draft-1",
            "version_id": "v5",
            "format": "markdown",
            "artifact_profile": "publication",
            "path": "/tmp/output/draft_reviews/handoff/scientist_review.md",
            "relative_path": "handoff/scientist_review.md",
            "saved_at": "2026-04-12T12:00:00Z",
            "metadata_available": True,
            "metadata_path": "/tmp/output/draft_reviews/handoff/scientist_review.md.meta.json"
        },
        "artifact_summary": {
            "ready_for_review": True,
            "validator_error_count": 0,
            "validator_warning_count": 2,
            "assay_cutoff_assessable_relationship_count": 1,
            "assay_cutoff_discordant_relationship_count": 0,
            "chemical_trace_included": False,
            "traced_key_event_count": 0,
            "active_key_event_count": 0,
            "total_gap_count": 3,
            "blocking_gap_count": 0,
            "advisory_gap_count": 3
        },
        "evidence_gap_summary": {
            "ready_for_review": True,
            "total_gap_count": 3,
            "blocking_gap_count": 0,
            "advisory_gap_count": 3,
            "global_gap_count": 1,
            "key_event_gap_count": 1,
            "relationship_gap_count": 1,
            "stressor_gap_count": 0,
            "assay_mapping_gap_count": 0
        },
        "linear_document": {
            "draft_id": "draft-1",
            "version_id": "v5",
            "title": "Scientific Draft Review: Draft AOP",
            "content": "## Handoff Context\n- Draft ID: draft-1\n",
            "project": "Tox Reviews",
            "issue": "AOP-123",
            "icon": ":microscope:",
            "source_reference": "handoff/scientist_review.md",
            "artifact_profile": "publication"
        },
        "suggested_create_document_arguments": {
            "title": "Scientific Draft Review: Draft AOP",
            "content": "## Handoff Context\n- Draft ID: draft-1\n",
            "project": "Tox Reviews",
            "issue": "AOP-123",
            "icon": ":microscope:"
        },
        "warnings": []
    }

    validate_payload(
        payload,
        namespace="read",
        name="plan_linear_draft_review_document.response.schema",
    )


def test_review_draft_evidence_gaps_schema_validation() -> None:
    payload = {
        "draft_id": "draft-1",
        "version_id": "v5",
        "draft": {
            "aop_entity_id": "AOP:draft-1",
            "title": "PXR activation leading to liver steatosis",
            "adverse_outcome": "Liver steatosis",
        },
        "review_parameters": {
            "assay_limit": 5,
            "stressor_limit": 10,
            "min_hitcall": 0.9,
        },
        "bundle_summary": {
            "ready_for_review": True,
            "validator_error_count": 0,
            "validator_warning_count": 4,
            "assay_cutoff_assessable_relationship_count": 0,
            "assay_cutoff_discordant_relationship_count": 0,
            "chemical_trace_included": False,
            "traced_key_event_count": 0,
            "active_key_event_count": 0,
            "total_gap_count": 7,
            "blocking_gap_count": 0,
            "advisory_gap_count": 7,
        },
        "summary": {
            "ready_for_review": True,
            "total_gap_count": 7,
            "blocking_gap_count": 0,
            "advisory_gap_count": 7,
            "global_gap_count": 2,
            "key_event_gap_count": 3,
            "relationship_gap_count": 1,
            "stressor_gap_count": 1,
            "assay_mapping_gap_count": 1,
        },
        "global_gaps": [
            {
                "id": "references_present",
                "severity": "warning",
                "category": "metadata",
                "title": "AOP root has references",
                "detail": "Add at least one reference supporting the AOP summary.",
                "source": "validation",
                "related_check_ids": ["references_present"],
            }
        ],
        "key_events": [
            {
                "id": "KE:1",
                "title": "PXR activation",
                "event_type": None,
                "event_role": "mie",
                "assay_candidate_count": 1,
                "top_assay_name": "ATG_PXRE_CIS",
                "top_assay_specificity_score": 0.75,
                "assay_search_limitations": [],
                "gap_count": 1,
                "gaps": [
                    {
                        "id": "missing_essentiality",
                        "severity": "warning",
                        "category": "essentiality",
                        "title": "Key event is missing explicit essentiality metadata",
                        "detail": "Provide a governed essentiality object even when the current call is `not_assessed` or `not_reported`.",
                        "source": "draft_record",
                        "related_check_ids": ["ke_essentiality_coverage"],
                    }
                ],
            }
        ],
        "relationships": [
            {
                "id": "KER:1",
                "source": "KE:1",
                "target": "KE:2",
                "type": "KeyEventRelationship",
                "plausibility": None,
                "status": None,
                "assay_cutoff_ordering_call": "not_reported",
                "assay_cutoff_supporting_chemical_count": 0,
                "gap_count": 1,
                "gaps": [
                    {
                        "id": "assay_cutoff_not_assessable",
                        "severity": "warning",
                        "category": "quantitative",
                        "title": "Assay cutoff ordering is not assessable for this KER",
                        "detail": "This relationship did not expose enough linked-stressor assay evidence for quantitative cutoff ordering review.",
                        "source": "quantitative_review",
                        "related_check_ids": ["ker_assay_cutoff_ordering_assessable"],
                    }
                ],
            }
        ],
        "stressors": [
            {
                "stressor_id": "CHEM:PFOS",
                "label": "PFOS",
                "source": "PFOS",
                "casrn": None,
                "dtxsid": None,
                "linked_target_ids": ["KE:1"],
                "searchable": True,
                "gap_count": 1,
                "gaps": [
                    {
                        "id": "missing_structured_identifier",
                        "severity": "warning",
                        "category": "stressor",
                        "title": "Stressor lacks a structured identifier",
                        "detail": "This stressor is only searchable by free text. Add a CAS RN or DTXSID for more reliable assay and quantitative evidence resolution.",
                        "source": "draft_record",
                        "related_check_ids": ["ker_assay_cutoff_ordering_assessable"],
                    }
                ],
            }
        ],
        "recommendations": [
            "Normalize linked stressors to CAS RN or DTXSID where possible so quantitative ordering review can resolve chemicals deterministically."
        ],
        "limitations": [
            "Chemical trace was not included because no chemical identifier was supplied."
        ],
    }

    validate_payload(
        payload,
        namespace="read",
        name="review_draft_evidence_gaps.response.schema",
    )


def test_list_assays_for_aop_schema_rejects_invalid_empty_reason() -> None:
    payload = {
        "results": [],
        "diagnostics": {
            "aop_id": "AOP:529",
            "comptox_api_key_configured": True,
            "stressor_count": 0,
            "chemical_match_count": 0,
            "bioactivity_hit_count": 0,
            "returned_assay_count": 0,
            "empty_reason": "wrong_value",
            "warnings": [],
        },
    }

    with pytest.raises(SchemaValidationError):
        validate_payload(payload, namespace="read", name="list_assays_for_aop.response.schema")
