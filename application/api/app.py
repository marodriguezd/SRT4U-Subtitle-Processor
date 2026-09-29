"""Local SRT4U REST API: a thin HTTP interface over application services.

GUI, CLI and API share the same ``SubtitleService`` / ``TranslationService`` /
``HistoryStore`` core. No business logic lives in the routes; the domain never
imports FastAPI.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .jobs import JobManager
from .routes import (
    analyze,
    benchmarks,
    health,
    history,
    jobs,
    pipeline,
    qa,
    transcribe,
    translate,
)

API_PREFIX = "/api/v1"


def create_app(job_manager: JobManager | None = None) -> FastAPI:
    """Application factory (a fresh JobManager per app unless given)."""
    app = FastAPI(
        title="SRT4U Subtitle Processor",
        description=(
            "API REST local sobre el núcleo existente de SRT4U: análisis, QA, "
            "traducción, procesamiento e historial. Uso local, sin autenticación."
        ),
        version="1.4.9",
    )
    app.state.jobs = job_manager if job_manager is not None else JobManager()

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN001, ANN202
        from .deps import logger as api_logger

        api_logger.error("Unhandled API error (%s)", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "error interno"})

    for module in (
        health,
        analyze,
        qa,
        translate,
        transcribe,
        pipeline,
        history,
        benchmarks,
        jobs,
    ):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
