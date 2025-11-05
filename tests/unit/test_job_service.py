from __future__ import annotations

from src.services.jobs import JobRecord, JobService, JobStatus


def test_submit_and_fetch_job() -> None:
    service = JobService()
    job = JobRecord(job_id="job-1", type="sparql")
    service.submit(job)

    stored = service.get("job-1")
    assert stored is not None
    assert stored.status == JobStatus.PENDING


def test_job_status_transitions() -> None:
    service = JobService()
    service.submit(JobRecord(job_id="job-1", type="sparql"))
    service.mark_running("job-1")
    assert service.get("job-1").status == JobStatus.RUNNING

    service.mark_succeeded("job-1", result={"rows": 10})
    stored = service.get("job-1")
    assert stored.status == JobStatus.SUCCEEDED
    assert stored.result == {"rows": 10}


def test_mark_failed_records_error() -> None:
    service = JobService()
    service.submit(JobRecord(job_id="job-1", type="sparql"))
    service.mark_failed("job-1", error="timeout")
    stored = service.get("job-1")
    assert stored.status == JobStatus.FAILED
    assert stored.error == "timeout"


def test_list_jobs_by_status() -> None:
    service = JobService()
    service.submit(JobRecord(job_id="job-1", type="sparql"))
    service.submit(JobRecord(job_id="job-2", type="publish"))
    service.mark_running("job-2")

    running = service.list(status=JobStatus.RUNNING)
    assert [job.job_id for job in running] == ["job-2"]

