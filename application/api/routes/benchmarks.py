"""Benchmark queries: read-only views over stored benchmark runs."""

from typing import List

from fastapi import APIRouter, HTTPException

from ..deps import open_history
from ..schemas import (
    BenchmarkDetailResponse,
    BenchmarkListResponse,
    BenchmarkSummaryModel,
)
from ...services.history_store import HistoryError

router = APIRouter(tags=["benchmarks"])


def _summaries() -> List[BenchmarkSummaryModel]:
    with open_history() as store:
        rows = store.recent_runs(limit=100000, operation="benchmark")
    grouped = {}
    for row in rows:
        benchmark_id = row.get("benchmark_id") or "unknown"
        entry = grouped.setdefault(
            benchmark_id, {"runs": 0, "providers": set(), "first_seen": None}
        )
        entry["runs"] += 1
        if row.get("requested_provider"):
            entry["providers"].add(str(row["requested_provider"]))
        timestamp = row.get("timestamp")
        if timestamp and (
            entry["first_seen"] is None or timestamp < entry["first_seen"]
        ):
            entry["first_seen"] = timestamp
    return [
        BenchmarkSummaryModel(
            benchmark_id=benchmark_id,
            runs=entry["runs"],
            providers=sorted(entry["providers"]),
            first_seen=entry["first_seen"],
        )
        for benchmark_id, entry in sorted(grouped.items())
    ]


@router.get(
    "/benchmarks",
    response_model=BenchmarkListResponse,
    summary="Lista benchmarks almacenados",
    description="Agregados por `benchmark_id` desde el historial. La ejecución "
    "de benchmarks no forma parte de la API.",
)
def list_benchmarks() -> BenchmarkListResponse:
    try:
        return BenchmarkListResponse(items=_summaries())
    except HistoryError as exc:
        raise HTTPException(status_code=500, detail="historial no disponible") from exc


@router.get(
    "/benchmarks/{benchmark_id}",
    response_model=BenchmarkDetailResponse,
    summary="Ejecuciones de un benchmark",
    description="Filas por (provider, run) de un `benchmark_id` concreto.",
    responses={404: {"description": "Benchmark inexistente"}},
)
def get_benchmark(benchmark_id: str) -> BenchmarkDetailResponse:
    try:
        with open_history() as store:
            rows = [
                row
                for row in store.recent_runs(limit=100000, operation="benchmark")
                if (row.get("benchmark_id") or "unknown") == benchmark_id
            ]
    except HistoryError as exc:
        raise HTTPException(status_code=500, detail="historial no disponible") from exc
    if not rows:
        raise HTTPException(status_code=404, detail="benchmark no encontrado")
    return BenchmarkDetailResponse(
        benchmark_id=benchmark_id,
        runs=[
            {
                key: row.get(key)
                for key in (
                    "provider",
                    "requested_provider",
                    "model",
                    "run_index",
                    "timestamp",
                    "number_of_cues",
                    "duration_ms",
                    "success",
                    "error_type",
                    "retry_count",
                    "fallback_used",
                    "providers_used",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "estimated_cost",
                )
            }
            for row in rows
        ],
    )
