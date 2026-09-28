"""History endpoints: read-only views over HistoryStore."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..deps import open_history
from ..schemas import HistoryItemModel, HistoryListResponse
from ...services.history_store import HistoryError

router = APIRouter(tags=["history"])


@router.get(
    "/history",
    response_model=HistoryListResponse,
    summary="Lista ejecuciones recientes",
    description="Historial local SQLite con filtros. Sin lenguaje de consulta.",
)
def list_history(
    provider: Optional[str] = Query(
        default=None, description="Filtra por provider solicitado"
    ),
    operation: Optional[str] = Query(
        default=None,
        description="process, analyze, qa, benchmark, transcription o pipeline",
    ),
    limit: int = Query(default=20, ge=1, le=1000, description="Máximo de filas"),
    errors_only: bool = Query(default=False, description="Solo ejecuciones fallidas"),
    fallback_only: bool = Query(
        default=False, description="Solo ejecuciones con fallback"
    ),
) -> HistoryListResponse:
    if operation is not None and operation not in {
        "process",
        "analyze",
        "qa",
        "benchmark",
        "transcription",
        "pipeline",
    }:
        raise HTTPException(status_code=422, detail="operation no válida")
    try:
        with open_history() as store:
            rows = store.recent_runs(
                limit=limit,
                provider=provider,
                operation=operation,
                only_errors=errors_only,
                only_fallbacks=fallback_only,
            )
    except HistoryError as exc:
        raise HTTPException(status_code=500, detail="historial no disponible") from exc
    items: List[HistoryItemModel] = []
    for row in rows:
        providers_used = row.get("providers_used")
        items.append(
            HistoryItemModel(
                **{
                    **row,
                    "providers_used": (
                        providers_used if isinstance(providers_used, list) else None
                    ),
                }
            )
        )
    return HistoryListResponse(items=items)


@router.get(
    "/history/{run_id}",
    response_model=HistoryItemModel,
    summary="Detalle de una ejecución",
    description="Una fila del historial por id.",
    responses={404: {"description": "Ejecución inexistente"}},
)
def get_history(run_id: int) -> HistoryItemModel:
    try:
        with open_history() as store:
            row = store.get_run(run_id)
    except HistoryError as exc:
        raise HTTPException(status_code=500, detail="historial no disponible") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="ejecución no encontrada")
    providers_used = row.get("providers_used")
    return HistoryItemModel(
        **{
            **row,
            "providers_used": (
                providers_used if isinstance(providers_used, list) else None
            ),
        }
    )
