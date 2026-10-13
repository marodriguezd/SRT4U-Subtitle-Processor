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
    summary="List recent execution runs",
    description="Local SQLite execution history with filters. No raw query language.",
)
def list_history(
    provider: Optional[str] = Query(
        default=None, description="Filter by requested provider"
    ),
    operation: Optional[str] = Query(
        default=None,
        description="process, analyze, qa, benchmark, transcription, or pipeline",
    ),
    limit: int = Query(default=20, ge=1, le=1000, description="Maximum rows to return"),
    errors_only: bool = Query(default=False, description="Only failed runs"),
    fallback_only: bool = Query(
        default=False, description="Only runs that used fallback"
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
        raise HTTPException(status_code=422, detail="invalid operation")
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
        raise HTTPException(
            status_code=500, detail="history store unavailable"
        ) from exc
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
    summary="Execution run details",
    description="A single history record by ID.",
    responses={404: {"description": "Run not found"}},
)
def get_history(run_id: int) -> HistoryItemModel:
    try:
        with open_history() as store:
            row = store.get_run(run_id)
    except HistoryError as exc:
        raise HTTPException(
            status_code=500, detail="history store unavailable"
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    providers_used = row.get("providers_used")
    return HistoryItemModel(
        **{
            **row,
            "providers_used": (
                providers_used if isinstance(providers_used, list) else None
            ),
        }
    )
