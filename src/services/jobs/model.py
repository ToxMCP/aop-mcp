"""Job record data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobRecord:
    job_id: str
    type: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    payload: Mapping[str, Any] = field(default_factory=dict)
    result: Mapping[str, Any] | None = None
    error: str | None = None

    def set_status(self, status: JobStatus, *, result: Mapping[str, Any] | None = None, error: str | None = None) -> None:
        self.status = status
        self.updated_at = _utcnow()
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error

