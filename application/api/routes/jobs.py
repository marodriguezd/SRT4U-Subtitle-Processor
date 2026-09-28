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
    summary="Lista jobs",
    description="Jobs locales en memoria (no persistentes).",
)
def list_jobs(request: Request, limit: int = 50) -> List[JobStatusResponse]:
    return [
        JobStatusResponse(**_public(job)) for job in _jobs_from(request).list(limit)
    ]


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Estado de un job",
    description="Incluye `result` al completarse o `error` al fallar.",
    responses={404: {"description": "Job inexistente"}},
)
def get_job(job_id: str, request: Request) -> JobStatusResponse:
    job = _jobs_from(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job no encontrado")
    return JobStatusResponse(**_public(job))


@router.delete(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Cancela un job",
    description="Best-effort: encolado se descarta; en ejecución termina y se "
    "descarta el resultado. Terminados devuelven 409.",
    responses={
        404: {"description": "Job inexistente"},
        409: {"description": "Job ya terminado"},
    },
)
def cancel_job(job_id: str, request: Request) -> JobStatusResponse:
    manager = _jobs_from(request)
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job no encontrado")
    if job["status"] in {"completed", "failed", "cancelled"}:
        raise HTTPException(
            status_code=409, detail=f"job ya terminado: {job['status']}"
        )
    manager.cancel(job_id)
    updated = manager.get(job_id)
    assert updated is not None
    return JobStatusResponse(**_public(updated))
