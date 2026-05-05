"""Utilities for verifying draft and MCP tool-call audit records."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterable

from src.services.draft_store import (
    Draft,
    compute_graph_checksum,
    compute_provenance_checksum,
)


SUPPORTED_CHECKSUM_ALGORITHMS = {"sha256-v1"}


def verify_audit_chain(draft: Draft) -> bool:
    """Verify that a draft's version chain is cryptographically intact.

    Checks:
    - checksum_algorithm is supported
    - checksum is present and matches recomputed graph hash
    - previous_checksum forms an unbroken chain across versions
    """
    if not draft.versions:
        return True
    previous_checksum = ""
    for version in draft.versions:
        metadata = version.metadata
        if metadata.checksum_algorithm not in SUPPORTED_CHECKSUM_ALGORITHMS:
            return False
        if not metadata.checksum:
            return False
        calculated = compute_graph_checksum(version.graph)
        if calculated != metadata.checksum:
            return False
        if metadata.previous_checksum != previous_checksum:
            return False
        previous_checksum = metadata.checksum
    return True


def verify_drafts(drafts: Iterable[Draft]) -> dict[str, bool]:
    return {draft.draft_id: verify_audit_chain(draft) for draft in drafts}


def verify_provenance_integrity(draft: Draft) -> bool:
    """Verify recorded provenance checksums for every draft version."""

    for version in draft.versions:
        metadata = version.metadata
        if metadata.provenance_checksum_algorithm not in SUPPORTED_CHECKSUM_ALGORITHMS:
            return False
        if not metadata.provenance_checksum:
            return False
        calculated = compute_provenance_checksum(metadata.provenance)
        if calculated != metadata.provenance_checksum:
            return False
    return True


def verify_draft_integrity(draft: Draft) -> dict[str, bool]:
    """Summarize graph-chain and provenance checksum verification for a draft."""

    audit_chain = verify_audit_chain(draft)
    provenance = verify_provenance_integrity(draft)
    return {
        "audit_chain": audit_chain,
        "provenance": provenance,
        "overall": audit_chain and provenance,
    }


@dataclass(frozen=True)
class ToolCallAuditRecord:
    """Immutable summary of one MCP tool-call attempt."""

    call_id: str
    tool_name: str
    started_at: str
    finished_at: str
    duration_ms: float
    status: str
    argument_keys: list[str]
    request_hash: str
    response_hash: str | None
    output_schema_title: str | None
    output_schema_hash: str | None
    output_validation_status: str
    risk_class: str | None
    required_scopes: list[str]
    granted_scopes: list[str]
    requires_confirmation: bool | None
    confirmation_provided: bool
    policy_status: str
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class InMemoryToolCallAuditLog:
    """Bounded process-local audit log for MCP dispatch records."""

    def __init__(self, max_records: int = 1000) -> None:
        self._max_records = max_records
        self._records: list[ToolCallAuditRecord] = []

    def append(self, record: ToolCallAuditRecord) -> None:
        self._records.append(record)
        if len(self._records) > self._max_records:
            del self._records[: len(self._records) - self._max_records]

    def list_records(self) -> list[ToolCallAuditRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()


tool_call_audit_log = InMemoryToolCallAuditLog()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hash_json(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=repr,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
