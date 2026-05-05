"""Utilities for verifying draft and MCP tool-call audit records."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from src.services.draft_store import (
    Draft,
    compute_graph_checksum,
    compute_provenance_checksum,
)


SUPPORTED_CHECKSUM_ALGORITHMS = {"sha256-v1"}
AUDIT_CHAIN_ALGORITHM = "sha256-json-v1"


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
        self._jsonl_sink: JsonlToolCallAuditSink | None = None
        self._last_persistence_error: str | None = None

    def configure_jsonl_sink(self, path: str | Path | None) -> None:
        self._jsonl_sink = JsonlToolCallAuditSink(path) if path else None
        self._last_persistence_error = None

    def append(self, record: ToolCallAuditRecord) -> None:
        self._records.append(record)
        if len(self._records) > self._max_records:
            del self._records[: len(self._records) - self._max_records]
        if self._jsonl_sink is not None:
            try:
                self._jsonl_sink.append(record)
                self._last_persistence_error = None
            except OSError as exc:
                self._last_persistence_error = str(exc)

    def list_records(self) -> list[ToolCallAuditRecord]:
        return list(self._records)

    def persistence_status(self) -> dict[str, object]:
        chain = self._jsonl_sink.chain_status() if self._jsonl_sink is not None else {
            "algorithm": AUDIT_CHAIN_ALGORITHM,
            "record_count": 0,
            "head_record_hash": None,
            "verified": None,
            "verification_error": None,
        }
        return {
            "enabled": self._jsonl_sink is not None,
            "path": str(self._jsonl_sink.path) if self._jsonl_sink is not None else None,
            "last_error": self._last_persistence_error,
            "chain": chain,
        }

    def clear(self) -> None:
        self._records.clear()


class JsonlToolCallAuditSink:
    """Append-only JSONL sink for durable MCP tool-call audit records."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def append(self, record: ToolCallAuditRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        chain = self.chain_status()
        if chain["verified"] is False:
            raise OSError(
                "Refusing to append to audit log with invalid hash chain: "
                + str(chain["verification_error"])
            )
        envelope = {
            "schema_version": "tool-call-audit-jsonl.v1",
            "algorithm": AUDIT_CHAIN_ALGORITHM,
            "sequence": int(chain["record_count"]) + 1,
            "previous_record_hash": chain["head_record_hash"],
            "record": record.to_dict(),
        }
        envelope["record_hash"] = hash_json(envelope)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    envelope,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                )
                + "\n"
            )

    def chain_status(self) -> dict[str, object]:
        record_count = 0
        previous_hash: str | None = None
        if not self.path.exists():
            return {
                "algorithm": AUDIT_CHAIN_ALGORITHM,
                "record_count": 0,
                "head_record_hash": None,
                "verified": True,
                "verification_error": None,
            }

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    envelope = json.loads(stripped)
                    expected_previous = envelope.get("previous_record_hash")
                    if expected_previous != previous_hash:
                        return _audit_chain_status_error(
                            record_count=record_count,
                            head_record_hash=previous_hash,
                            message=f"Line {line_number} previous_record_hash does not match chain head.",
                        )
                    recorded_hash = envelope.get("record_hash")
                    envelope_without_hash = dict(envelope)
                    envelope_without_hash.pop("record_hash", None)
                    calculated_hash = hash_json(envelope_without_hash)
                    if recorded_hash != calculated_hash:
                        return _audit_chain_status_error(
                            record_count=record_count,
                            head_record_hash=previous_hash,
                            message=f"Line {line_number} record_hash does not match record contents.",
                        )
                    if envelope.get("algorithm") != AUDIT_CHAIN_ALGORITHM:
                        return _audit_chain_status_error(
                            record_count=record_count,
                            head_record_hash=previous_hash,
                            message=f"Line {line_number} uses unsupported audit chain algorithm.",
                        )
                    record_count += 1
                    previous_hash = recorded_hash
        except (OSError, json.JSONDecodeError) as exc:
            return _audit_chain_status_error(
                record_count=record_count,
                head_record_hash=previous_hash,
                message=str(exc),
            )

        return {
            "algorithm": AUDIT_CHAIN_ALGORITHM,
            "record_count": record_count,
            "head_record_hash": previous_hash,
            "verified": True,
            "verification_error": None,
        }


def _audit_chain_status_error(
    *,
    record_count: int,
    head_record_hash: str | None,
    message: str,
) -> dict[str, object]:
    return {
        "algorithm": AUDIT_CHAIN_ALGORITHM,
        "record_count": record_count,
        "head_record_hash": head_record_hash,
        "verified": False,
        "verification_error": message,
    }


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
