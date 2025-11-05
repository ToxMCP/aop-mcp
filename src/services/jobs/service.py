"""In-memory job management for async operations."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Iterable, Protocol

from .model import JobRecord, JobStatus
from src.instrumentation.logging import StructuredLogger


class JobBackend(Protocol):
    def enqueue(self, job: JobRecord) -> JobRecord:
        ...

    def get(self, job_id: str) -> JobRecord | None:
        ...

    def list(self, *, status: JobStatus | None = None) -> Iterable[JobRecord]:
        ...

    def update(self, job_id: str, *, status: JobStatus, result=None, error: str | None = None) -> JobRecord:
        ...


class InMemoryJobBackend(JobBackend):
    def __init__(self) -> None:
        self._records: Dict[str, JobRecord] = {}

    def enqueue(self, job: JobRecord) -> JobRecord:
        if job.job_id in self._records:
            raise ValueError(f"Job '{job.job_id}' already exists")
        self._records[job.job_id] = job
        return job

    def get(self, job_id: str) -> JobRecord | None:
        record = self._records.get(job_id)
        return replace(record) if record else None

    def list(self, *, status: JobStatus | None = None) -> Iterable[JobRecord]:
        for record in self._records.values():
            if status is None or record.status == status:
                yield replace(record)

    def update(self, job_id: str, *, status: JobStatus, result=None, error: str | None = None) -> JobRecord:
        record = self._records.get(job_id)
        if record is None:
            raise KeyError(f"Job '{job_id}' not found")
        record.set_status(status, result=result, error=error)
        return replace(record)


class JobService:
    def __init__(self, backend: JobBackend | None = None, logger: StructuredLogger | None = None) -> None:
        self._backend = backend or InMemoryJobBackend()
        self._logger = logger or StructuredLogger("job-service")

    def submit(self, job: JobRecord) -> JobRecord:
        stored = self._backend.enqueue(job)
        self._logger.info("job_submitted", job_id=stored.job_id, job_type=stored.type)
        return stored

    def mark_running(self, job_id: str) -> JobRecord:
        record = self._backend.update(job_id, status=JobStatus.RUNNING)
        self._logger.info("job_running", job_id=record.job_id)
        return record

    def mark_succeeded(self, job_id: str, *, result=None) -> JobRecord:
        record = self._backend.update(job_id, status=JobStatus.SUCCEEDED, result=result)
        self._logger.info("job_succeeded", job_id=record.job_id)
        return record

    def mark_failed(self, job_id: str, *, error: str) -> JobRecord:
        record = self._backend.update(job_id, status=JobStatus.FAILED, error=error)
        self._logger.error("job_failed", job_id=record.job_id, error=error)
        return record

    def cancel(self, job_id: str) -> JobRecord:
        record = self._backend.update(job_id, status=JobStatus.CANCELLED)
        self._logger.warning("job_cancelled", job_id=record.job_id)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        return self._backend.get(job_id)

    def list(self, *, status: JobStatus | None = None) -> list[JobRecord]:
        return list(self._backend.list(status=status))
