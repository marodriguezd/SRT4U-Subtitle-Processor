"""Local SRT4U REST API: a thin HTTP interface over application services.

GUI, CLI and API share the same ``SubtitleService`` / ``TranslationService`` /
``HistoryStore`` core. No business logic lives in the routes; the domain never
imports FastAPI.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .jobs import JobManager
from .schemas import (
    APP_VERSION,
    ProcessResultModel,
    TranscriptionResultModel,
    TranslationResultModel,
)
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
        version=APP_VERSION,
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

    # Slow operations (translate/process/transcribe/pipeline) run as
    # JobManager jobs and their payload travels inside
    # JobStatusResponse.result, so FastAPI cannot infer the result shape
    # while generating OpenAPI. Extend the generated schema so `result` is
    # documented as the union of the job-result models (the routes already
    # build those payloads with these very models — no business logic is
    # duplicated), and ProcessResultModel keeps declaring parse_issues.
    # Runtime responses stay plain dicts (the field is Dict[str, Any]); this
    # only documents the served contract.
    # (Standard "extending OpenAPI" pattern: wrap the generator, keep its
    # cache, and only add what is missing.)
    original_openapi = app.openapi
    job_result_models = (
        ProcessResultModel,
        TranslationResultModel,
        TranscriptionResultModel,
    )

    def openapi_with_result_models():  # noqa: ANN202
        schema = original_openapi()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in job_result_models:
            if model.__name__ not in components:
                model_schema = model.model_json_schema(
                    ref_template="#/components/schemas/{model}"
                )
                definitions = model_schema.pop("$defs", {})
                components.setdefault(model.__name__, model_schema)
                for name, sub_schema in definitions.items():
                    components.setdefault(name, sub_schema)
        job_status = components.setdefault("JobStatusResponse", {})
        job_status.setdefault("properties", {})["result"] = {
            "description": (
                "Job payload; shape depends on `operation`: `process` → "
                "ProcessResultModel (includes `parse_issues`), `translate` → "
                "TranslationResultModel, `transcription` → "
                "TranscriptionResultModel, `pipeline` → pipeline result object "
                "(success/stages/parse_issues/…)."
            ),
            "anyOf": [{"type": "null"}]
            + [
                {"$ref": f"#/components/schemas/{model.__name__}"}
                for model in job_result_models
            ],
        }
        return schema

    app.openapi = openapi_with_result_models
    return app


app = create_app()
