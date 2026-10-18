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
    """Aggregated benchmark list; grouping happens in SQLite, not in Python."""
    with open_history() as store:
        rows = store.benchmark_summaries()
    return [BenchmarkSummaryModel(**row) for row in rows]


@router.get(
    "/benchmarks",
    response_model=BenchmarkListResponse,
    summary="List stored benchmarks",
    description="Aggregated by `benchmark_id` from execution history. "
    "Benchmark execution is CLI-only.",
)
def list_benchmarks() -> BenchmarkListResponse:
    try:
        return BenchmarkListResponse(items=_summaries())
    except HistoryError as exc:
        raise HTTPException(
            status_code=500, detail="history store unavailable"
        ) from exc


@router.get(
    "/benchmarks/{benchmark_id}",
    response_model=BenchmarkDetailResponse,
    summary="Runs for a benchmark",
    description="Per-(provider, run) records for a specific `benchmark_id`.",
    responses={404: {"description": "Benchmark not found"}},
)
def get_benchmark(benchmark_id: str) -> BenchmarkDetailResponse:
    try:
        with open_history() as store:
            rows = store.recent_runs(
                limit=100000,
                operation="benchmark",
                benchmark_id=benchmark_id,
            )
    except HistoryError as exc:
        raise HTTPException(
            status_code=500, detail="history store unavailable"
        ) from exc
    if not rows:
        raise HTTPException(status_code=404, detail="benchmark not found")
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
