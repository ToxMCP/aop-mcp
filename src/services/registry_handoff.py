from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, Mapping

from pydantic import BaseModel, Field, model_validator

IMPORTED_REGISTRY_SUPPORT_KEY = "imported_registry_support"


class TypedHandoffRef(BaseModel):
    objectType: Literal["typedHandoffRef"] = "typedHandoffRef"
    schemaVersion: str = "1.1.0"
    objectTypeRef: str
    retrievalEndpoint: str | None = None
    cachedSnapshot: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    artifactId: str | None = None
    producerModule: str | None = None
    producerVersion: str | None = None
    integrityHash: str | None = None

    @model_validator(mode="after")
    def _validate_presence(self) -> "TypedHandoffRef":
        if not self.retrievalEndpoint and self.cachedSnapshot is None:
            raise ValueError(
                "typed handoff refs must provide retrievalEndpoint or cachedSnapshot"
            )
        return self


class HandoffProvenance(BaseModel):
    toolRunId: str
    createdAt: str | None = None
    createdBy: str | None = None
    sourceHashes: list[dict[str, str]] = Field(default_factory=list)
    parentObjectIds: list[str] = Field(default_factory=list)
    upstreamRunIds: list[str] = Field(default_factory=list)


class StudyIdentifier(BaseModel):
    identifierType: str
    identifierValue: str


class RegistryEvidenceItem(BaseModel):
    originalId: str
    evidenceClass: Literal["method_quality"]
    sourceModule: Literal["evidence_registry"]
    provenance: HandoffProvenance
    endpointFamily: str | None = None
    biologicalLevel: str | None = None
    methodMaturity: str | None = None
    methodDescription: str | None = None
    studyIdentifiers: list[StudyIdentifier] = Field(default_factory=list)
    schemaVersion: str = "1.1.0"
    readinessState: str | None = None
    reviewCaveats: list[str] = Field(default_factory=list)
    scientificReviewGapIds: list[str] = Field(default_factory=list)
    registryArtifactRefs: list[TypedHandoffRef] = Field(default_factory=list)


class RegistryClaimItem(BaseModel):
    originalId: str
    claimText: str
    claimType: str | None = None
    supportStatus: str
    confidence: str
    evidenceObjectIds: list[str] = Field(default_factory=list)
    lineOfEvidenceId: str | None = None
    rationale: str | None = None
    provenance: HandoffProvenance
    applicabilityRecordId: str | None = None


class RegistryApplicabilityAssessment(BaseModel):
    dimension: str
    status: Literal["direct", "partial", "indirect", "not_comparable"]
    rationale: str
    bridgingRationale: str | None = None
    evidenceValue: str | None = None
    targetValue: str | None = None


class RegistryApplicabilityItem(BaseModel):
    originalId: str
    evidenceClass: Literal["method_quality"]
    intendedUse: str
    dimensionAssessments: list[RegistryApplicabilityAssessment]
    overallStatus: Literal["direct", "partial", "indirect", "not_comparable"]
    materiality: str
    affectedObjectIds: list[str] = Field(default_factory=list)
    provenance: HandoffProvenance
    gapTriggered: bool | None = None
    reviewFlag: str | None = None


class RegistryArtifactPayloads(BaseModel):
    handoffBundle: dict[str, Any]
    reviewPacket: dict[str, Any]
    readinessRecords: list[dict[str, Any]]
    routingRecommendation: dict[str, Any]
    evidenceQualityReview: dict[str, Any] | None = None
    overinterpretationWarningRegister: dict[str, Any] | None = None
    semanticLossRegister: dict[str, Any]
    canonicalRecords: list[dict[str, Any]]


class RegistryDownstreamHandoffBundle(BaseModel):
    sourceFormat: Literal["structured_json_bundle"]
    sourceVersion: Literal["1.1.0"]
    bundleId: str
    schemaVersion: str = "1.1.0"
    createdAt: str
    createdBy: Literal["evidence_registry"]
    targetConsumer: Literal["aop_context"]
    evidenceItems: list[RegistryEvidenceItem]
    claimItems: list[RegistryClaimItem] = Field(default_factory=list)
    linkItems: list[dict[str, Any]] = Field(default_factory=list)
    applicabilityItems: list[RegistryApplicabilityItem] = Field(default_factory=list)
    registryArtifactRefs: list[TypedHandoffRef]
    registryArtifacts: RegistryArtifactPayloads


def normalize_registry_handoff_bundle(bundle_payload: dict[str, Any]) -> dict[str, Any]:
    bundle = RegistryDownstreamHandoffBundle.model_validate(bundle_payload)
    return bundle.model_dump(exclude_none=True)


def _imported_registry_support_bundles(
    provenance: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if provenance is None:
        return []
    raw_items = provenance.get(IMPORTED_REGISTRY_SUPPORT_KEY, [])
    if not isinstance(raw_items, list):
        raise ValueError(
            "draft provenance field 'imported_registry_support' must be a list of Registry handoff bundles"
        )

    bundles: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            raise ValueError(
                "draft provenance field 'imported_registry_support' must contain only bundle objects"
            )
        bundles.append(normalize_registry_handoff_bundle(dict(item)))
    return bundles


def merge_registry_support_provenance(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = {
        str(key): deepcopy(value)
        for key, value in dict(existing or {}).items()
        if key != IMPORTED_REGISTRY_SUPPORT_KEY
    }
    for key, value in dict(incoming or {}).items():
        if key == IMPORTED_REGISTRY_SUPPORT_KEY:
            continue
        merged[str(key)] = deepcopy(value)

    bundles_by_id: dict[str, dict[str, Any]] = {}
    ordered_bundle_ids: list[str] = []
    for bundle in _imported_registry_support_bundles(existing):
        bundle_id = str(bundle["bundleId"])
        if bundle_id not in bundles_by_id:
            ordered_bundle_ids.append(bundle_id)
        bundles_by_id[bundle_id] = bundle
    for bundle in _imported_registry_support_bundles(incoming):
        bundle_id = str(bundle["bundleId"])
        if bundle_id not in bundles_by_id:
            ordered_bundle_ids.append(bundle_id)
        bundles_by_id[bundle_id] = bundle

    if ordered_bundle_ids:
        merged[IMPORTED_REGISTRY_SUPPORT_KEY] = [
            deepcopy(bundles_by_id[bundle_id]) for bundle_id in ordered_bundle_ids
        ]

    return merged


def _warning_messages(bundle: RegistryDownstreamHandoffBundle) -> list[str]:
    register = bundle.registryArtifacts.overinterpretationWarningRegister or {}
    warnings = register.get("warnings", [])
    output: list[str] = []
    for warning in warnings:
        warning_class = warning.get("warning_class")
        message = warning.get("message")
        if isinstance(warning_class, str) and isinstance(message, str):
            output.append(f"{warning_class}: {message}")
    return output


def _scientific_review_flags(bundle: RegistryDownstreamHandoffBundle) -> list[str]:
    quality = bundle.registryArtifacts.evidenceQualityReview or {}
    reasons = quality.get("manual_review_reasons", [])
    flags = quality.get("unresolved_study_design_flags", [])
    output = [
        reason for reason in reasons if isinstance(reason, str) and reason.strip()
    ]
    output.extend(
        f"study_design_flag: {flag}"
        for flag in flags
        if isinstance(flag, str) and flag.strip()
    )
    return output


def _suggested_draft_title(bundle: RegistryDownstreamHandoffBundle) -> str | None:
    for record in bundle.registryArtifacts.canonicalRecords:
        title = record.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return None


def _suggested_references(bundle: RegistryDownstreamHandoffBundle) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for record in bundle.registryArtifacts.canonicalRecords:
        title = record.get("title")
        if not isinstance(title, str) or not title.strip():
            title = record.get("object_type")
        accessions = record.get("source_accessions", [])
        accession: str | None = None
        if isinstance(accessions, list):
            first_accession = next(
                (
                    item
                    for item in accessions
                    if isinstance(item, str) and item.strip()
                ),
                None,
            )
            accession = first_accession
        if accession is None:
            source_refs = record.get("source_refs", [])
            if isinstance(source_refs, list):
                for source_ref in source_refs:
                    if (
                        isinstance(source_ref, dict)
                        and isinstance(source_ref.get("accession"), str)
                        and source_ref["accession"].strip()
                    ):
                        accession = source_ref["accession"].strip()
                        break
        references.append(
            {
                "label": title,
                "accession": accession,
                "record_id": record.get("record_id"),
                "note": (
                    "Registry-imported supporting evidence; preserve bounded-use caveats "
                    "and do not treat as direct KE/KER proof without additional empirical support."
                ),
            }
        )
    return references


def build_registry_handoff_review(bundle_payload: dict[str, Any]) -> dict[str, Any]:
    bundle = RegistryDownstreamHandoffBundle.model_validate(bundle_payload)

    direct_applicability_count = sum(
        1 for item in bundle.applicabilityItems if item.overallStatus == "direct"
    )
    partial_applicability_count = sum(
        1 for item in bundle.applicabilityItems if item.overallStatus == "partial"
    )
    indirect_applicability_count = sum(
        1 for item in bundle.applicabilityItems if item.overallStatus == "indirect"
    )
    not_comparable_applicability_count = sum(
        1
        for item in bundle.applicabilityItems
        if item.overallStatus == "not_comparable"
    )

    bounded_use_warnings = _warning_messages(bundle)
    scientific_review_flags = _scientific_review_flags(bundle)
    ready_for_aop_review = (
        len(bundle.evidenceItems) > 0 and not_comparable_applicability_count == 0
    )

    evidence_items = [
        {
            "original_id": item.originalId,
            "method_description": item.methodDescription,
            "method_maturity": item.methodMaturity,
            "readiness_state": item.readinessState,
            "study_identifiers": [
                {
                    "identifier_type": identifier.identifierType,
                    "identifier_value": identifier.identifierValue,
                }
                for identifier in item.studyIdentifiers
            ],
            "review_caveats": item.reviewCaveats,
            "scientific_review_gap_ids": item.scientificReviewGapIds,
            "registry_artifact_refs": [
                ref.model_dump(exclude_none=True) for ref in item.registryArtifactRefs
            ],
        }
        for item in bundle.evidenceItems
    ]

    draft_import_plan = {
        "suggested_draft_title": _suggested_draft_title(bundle),
        "suggested_adverse_outcome": None,
        "suggested_ke_support_actions": [
            "Map the imported Registry support manually to the relevant draft key event(s); the handoff bundle preserves supporting evidence but does not identify KE targets automatically.",
            "Use Registry evidence as supporting mechanistic context or bounded essentiality/applicability rationale only where the draft author can justify the mapping.",
        ],
        "suggested_ker_support_actions": [
            "Use the imported Registry bundle to support bounded plausibility or contextual rationale for relevant KER review sections, not as automatic empirical-support proof.",
            "Keep all imported scientific-review gaps and overinterpretation warnings visible when citing Registry evidence in KER review text.",
        ],
        "suggested_stressor_link_actions": [
            "Only create stressor links when the draft author can trace the Registry evidence to a concrete chemical/stressor identity already supported by AOP or CompTox-side evidence.",
        ],
        "required_manual_mapping": [
            "Manual KE/KER mapping is required before Registry evidence can be attached to draft-specific review claims.",
            "Imported AOP-context bundles preserve provenance and caveats, but they do not establish causal directionality or direct empirical sufficiency on their own.",
        ],
        "suggested_references": _suggested_references(bundle),
        "attachable_registry_artifact_refs": [
            ref.model_dump(exclude_none=True) for ref in bundle.registryArtifactRefs
        ],
    }

    limitations = [
        "Registry handoff bundles for AOP context preserve supporting evidence, provenance, and bounded-use caveats but do not establish KE or KER truth automatically.",
        "Imported Registry evidence must remain reviewable support and should not silently replace direct AOP-Wiki, AOP-DB, or empirical assay evidence.",
    ]

    return {
        "source": {
            "bundle_id": bundle.bundleId,
            "source_version": bundle.sourceVersion,
            "created_at": bundle.createdAt,
            "target_consumer": bundle.targetConsumer,
        },
        "summary": {
            "ready_for_aop_review": ready_for_aop_review,
            "evidence_item_count": len(bundle.evidenceItems),
            "claim_item_count": len(bundle.claimItems),
            "applicability_item_count": len(bundle.applicabilityItems),
            "direct_applicability_count": direct_applicability_count,
            "partial_applicability_count": partial_applicability_count,
            "indirect_applicability_count": indirect_applicability_count,
            "not_comparable_applicability_count": not_comparable_applicability_count,
            "blocking_issue_count": not_comparable_applicability_count,
            "advisory_issue_count": len(bounded_use_warnings)
            + len(scientific_review_flags)
            + partial_applicability_count
            + indirect_applicability_count,
        },
        "evidence_items": evidence_items,
        "bounded_use_warnings": bounded_use_warnings,
        "scientific_review_flags": scientific_review_flags,
        "draft_import_plan": draft_import_plan,
        "limitations": limitations,
    }


def build_imported_registry_support_summary(
    provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    imports = [
        build_registry_handoff_review(bundle)
        for bundle in _imported_registry_support_bundles(provenance)
    ]
    limitations = list(
        dict.fromkeys(
            limitation
            for item in imports
            for limitation in item.get("limitations", [])
            if isinstance(limitation, str) and limitation.strip()
        )
    )

    if any(
        item["summary"]["not_comparable_applicability_count"] > 0 for item in imports
    ):
        limitations.append(
            "One or more imported Registry bundles include non-comparable applicability and should not be cited as usable AOP support without manual review."
        )

    return {
        "summary": {
            "attached_bundle_count": len(imports),
            "ready_bundle_count": sum(
                1 for item in imports if item["summary"]["ready_for_aop_review"]
            ),
            "total_evidence_item_count": sum(
                item["summary"]["evidence_item_count"] for item in imports
            ),
            "total_bounded_use_warning_count": sum(
                len(item["bounded_use_warnings"]) for item in imports
            ),
            "total_scientific_review_flag_count": sum(
                len(item["scientific_review_flags"]) for item in imports
            ),
            "blocking_issue_count": sum(
                item["summary"]["blocking_issue_count"] for item in imports
            ),
            "advisory_issue_count": sum(
                item["summary"]["advisory_issue_count"] for item in imports
            ),
        },
        "imports": imports,
        "limitations": limitations,
    }
