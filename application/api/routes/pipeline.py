"""Pipeline endpoint: the full media pipeline runs as a JobManager job."""

from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..deps import MAX_UPLOAD_BYTES, remove_temp, safe_detail, save_upload
from ..jobs import JobError, JobManager
from ..schemas import JobCreatedResponse
from ...services.media_pipeline import (
    EXPORT_FORMATS,
    MEDIA_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    MediaPipeline,
    PipelineConfig,
    PipelineConfigError,
)
from ...services.transcription_whisper import WHISPER_MODELS

router = APIRouter(tags=["pipeline"])

_pipeline_note = (
    "Pipeline audiovisual completa (transcripción → limpieza → analytics → "
    "QA → traducción opcional → QA final → exportación → burn-in opcional). "
    "Operación larga: se encola un job local y se consulta en /jobs/{id}."
)


def _jobs_from(request: Request) -> JobManager:
    return request.app.state.jobs


def _validate_pipeline_extension(filename: Optional[str]) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in MEDIA_EXTENSIONS and suffix not in SUBTITLE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"formato de entrada no soportado: {suffix or '(sin extensión)'}",
        )
    return suffix


@router.post(
    "/pipeline",
    response_model=JobCreatedResponse,
    status_code=202,
    summary="Pipeline audiovisual completa (job)",
    description=_pipeline_note,
)
async def pipeline(
    request: Request,
    file: UploadFile = File(  # noqa: B008
        description="Audio, vídeo o subtítulo de entrada"
    ),
    transcribe: Annotated[
        bool, Form(description="Transcribe la entrada multimedia")
    ] = True,  # noqa: B008
    model: Annotated[str, Form(description="Modelo Whisper")] = "small",  # noqa: B008
    language: Annotated[str, Form(description="Idioma o auto")] = "auto",  # noqa: B008
    device: Annotated[str, Form(description="auto, cpu o cuda")] = "auto",  # noqa: B008
    clean: Annotated[bool, Form(description="Limpieza")] = True,  # noqa: B008
    qa: Annotated[bool, Form(description="QA determinista")] = True,  # noqa: B008
    strict: Annotated[
        bool, Form(description="QA estricto detiene la pipeline")
    ] = False,  # noqa: B008
    translate: Annotated[bool, Form(description="Traducción")] = False,  # noqa: B008
    source_language: Annotated[str, Form(description="Idioma de origen")] = "auto",  # noqa: B008
    target_language: Annotated[
        Optional[str], Form(description="Idioma de destino")
    ] = None,  # noqa: B008
    provider: Annotated[
        str, Form(description="google, deepl, openai, ollama, llm")
    ] = "google",  # noqa: B008
    max_retries: Annotated[int, Form(description="Reintentos")] = 0,  # noqa: B008
    no_fallback: Annotated[bool, Form(description="Desactiva el fallback")] = False,  # noqa: B008
    output_format: Annotated[str, Form(description="srt o vtt")] = "srt",  # noqa: B008
) -> JobCreatedResponse:
    suffix = _validate_pipeline_extension(file.filename)
    is_media = suffix in MEDIA_EXTENSIONS
    if is_media and not transcribe:
        raise HTTPException(
            status_code=422,
            detail="la entrada es audio/vídeo pero la transcripción está desactivada",
        )
    if model not in WHISPER_MODELS:
        raise HTTPException(
            status_code=422,
            detail=f"modelo no soportado: {model}",
        )
    if output_format not in EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail="output_format debe ser srt o vtt")
    if device not in {"auto", "cpu", "cuda"}:
        raise HTTPException(status_code=422, detail="device debe ser auto, cpu o cuda")
    if translate and not (target_language or "").strip():
        raise HTTPException(
            status_code=422, detail="target_language es obligatorio al traducir"
        )
    if max_retries < 0 or max_retries > 10:
        raise HTTPException(
            status_code=422, detail="max_retries debe estar entre 0 y 10"
        )
    limit = MAX_UPLOAD_BYTES if not is_media else 500 * 1024 * 1024
    tmp_path = await save_upload(file, suffix, max_bytes=limit)
    filename = file.filename or f"input{suffix}"
    # The export stage always writes to disk: point it at a sibling temp file
    # (deleted afterwards) so server paths never leak into the response.
    export_tmp = tmp_path.with_name(f"{tmp_path.stem}_pipeline.{output_format}")

    def _cleanup() -> None:
        remove_temp(tmp_path)
        remove_temp(export_tmp)

    try:
        config = PipelineConfig(
            input_media=str(tmp_path),
            output_subtitle=str(export_tmp),
            transcription_enabled=transcribe,
            transcription_model=model,
            transcription_language=language,
            transcription_device=device,
            clean_enabled=clean,
            qa_enabled=qa,
            qa_strict=strict,
            translation_enabled=translate,
            source_language=source_language,
            target_language=target_language,
            provider=provider,
            max_retries=max_retries,
            fallback_enabled=not no_fallback,
            output_format=output_format,
            burn_in_enabled=False,
        ).validate()
    except PipelineConfigError as exc:
        _cleanup()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def _work() -> dict:
        from ...services.media_pipeline import record_pipeline_result

        try:
            result = MediaPipeline().run(config)
            try:
                record_pipeline_result(result, config, file_path=filename)
            except Exception:
                pass
            payload = result.to_dict()
            payload["input_filename"] = filename
            payload["output_subtitle"] = None
            return payload
        except PipelineConfigError as exc:
            raise JobError(safe_detail(exc)) from exc
        except Exception as exc:  # job boundary: sanitize
            from ..deps import logger as api_logger

            api_logger.exception("Pipeline job failed")
            raise JobError(safe_detail(exc)) from exc
        finally:
            _cleanup()

    job_id = _jobs_from(request).submit("pipeline", _work, on_drop=_cleanup)
    return JobCreatedResponse(job_id=job_id, status="queued")
