"""Utilities for verifying draft audit chains."""

from __future__ import annotations

from typing import Iterable

from src.services.draft_store import Draft, compute_graph_checksum


def verify_audit_chain(draft: Draft) -> bool:
    if not draft.versions:
        return True
    previous_checksum = None
    for version in draft.versions:
        calculated = compute_graph_checksum(version.graph)
        if calculated != version.metadata.checksum:
            return False
        if previous_checksum is not None and version.metadata.previous_checksum != previous_checksum:
            return False
        previous_checksum = version.metadata.checksum
    return True


def verify_drafts(drafts: Iterable[Draft]) -> dict[str, bool]:
    return {draft.draft_id: verify_audit_chain(draft) for draft in drafts}

