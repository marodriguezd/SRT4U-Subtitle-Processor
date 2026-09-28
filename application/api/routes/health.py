"""Liveness probe; deliberately cheap."""

from fastapi import APIRouter

from ..schemas import APP_VERSION, HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado del servicio",
    description="Sonda de vida sin comprobaciones pesadas.",
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=APP_VERSION)
