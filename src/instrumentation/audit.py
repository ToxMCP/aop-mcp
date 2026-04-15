"""Utilities for verifying draft audit chains."""

from __future__ import annotations

from typing import Iterable

from src.services.draft_store import Draft, compute_graph_checksum


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

