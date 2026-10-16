"""Job inspection endpoints for translate/process background work."""

from typing import List

from fastapi import APIRouter, HTTPException, Request

from ..jobs import JobManager
from ..schemas import JobStatusResponse

router = APIRouter(tags=["jobs"])


def _jobs_from(request: Request) -> JobManager:
    return request.app.state.jobs


def _public(job: dict) -> dict:
    return {
        key: job.get(key)
        for key in (
            "job_id",
            "operation",
            "status",
            "created_at",
            "finished_at",
            "error",
            "result",
        )
    }


@router.get(
    "/jobs",
    response_model=List[JobStatusResponse],
    summary="List jobs",
    description="In-memory local jobs (not persistent across restarts).",
)
def list_jobs(request: Request, limit: int = 50) -> List[JobStatusResponse]:
    return [
        JobStatusResponse(**_public(job)) for job in _jobs_from(request).list(limit)
    ]


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Includes `result` on completion or `error` on failure.",
    responses={404: {"description": "Job not found"}},
)
def get_job(job_id: str, request: Request) -> JobStatusResponse:
    job = _jobs_from(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(**_public(job))


@router.delete(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Cancel a job",
    description="Best-effort: queued jobs are dropped; running jobs finish and "
    "their result is discarded. Finished jobs return 409.",
    responses={
        404: {"description": "Job not found"},
        409: {"description": "Job already finished"},
    },
)
def cancel_job(job_id: str, request: Request) -> JobStatusResponse:
    manager = _jobs_from(request)
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] in {"completed", "failed", "cancelled"}:
        raise HTTPException(
            status_code=409, detail=f"job already finished: {job['status']}"
        )
    manager.cancel(job_id)
    updated = manager.get(job_id)
    if updated is None:
        return JobStatusResponse(
            job_id=job_id,
            operation=job["operation"],
            status="cancelled",
            created_at=job.get("created_at"),
            finished_at=job.get("finished_at"),
            error=None,
            result=None,
        )
    return JobStatusResponse(**_public(updated))
