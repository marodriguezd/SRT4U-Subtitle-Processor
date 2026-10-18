"""Transcribe endpoint: slow local Whisper work runs as a JobManager job."""

from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..deps import remove_temp, safe_detail, sanitize_upload_filename, save_upload
from ..jobs import JobError, JobManager
from ..schemas import JobCreatedResponse, TranscriptionResultModel
from ...services.history_store import HistoryStore
from ...services.transcription_providers import TranscriptionError
from ...services.transcription_service import MEDIA_EXTENSIONS, TranscriptionService
from ...services.transcription_whisper import WHISPER_MODELS

router = APIRouter(tags=["transcribe"])

TRANSCRIBE_MAX_BYTES = 500 * 1024 * 1024

_transcribe_note = (
    "Local Whisper transcription can take time: queues a local job "
    "polled at /jobs/{id}. Requires the 'transcription' optional extra. "
    "User media is never sent to external services."
)


def _jobs_from(request: Request) -> JobManager:
    return request.app.state.jobs


def _validate_media_extension(filename: Optional[str]) -> str:
    from pathlib import Path

    suffix = Path(filename or "").suffix.lower()
    if suffix not in MEDIA_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported media format: {suffix or '(no extension)'}",
        )
    return suffix


@router.post(
    "/transcribe",
    response_model=JobCreatedResponse,
    status_code=202,
    summary="Transcribe audio/video (job)",
    description=_transcribe_note,
)
async def transcribe(
    request: Request,
    file: UploadFile = File(  # noqa: B008
        description="Audio or video file (mp4, mkv, mp3, wav, ...)"
    ),
    model: Annotated[
        str, Form(description="tiny, base, small, medium, large-v3, turbo")
    ] = "small",  # noqa: B008
    language: Annotated[str, Form(description="Language code or auto")] = "auto",  # noqa: B008
    output_format: Annotated[str, Form(description="srt or vtt")] = "srt",  # noqa: B008
    device: Annotated[str, Form(description="auto, cpu, or cuda")] = "auto",  # noqa: B008
) -> JobCreatedResponse:
    suffix = _validate_media_extension(file.filename)
    if model not in WHISPER_MODELS:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported model: {model} (supported: {', '.join(WHISPER_MODELS)})",
        )
    if output_format not in {"srt", "vtt"}:
        raise HTTPException(status_code=422, detail="output_format must be srt or vtt")
    if device not in {"auto", "cpu", "cuda"}:
        raise HTTPException(status_code=422, detail="device must be auto, cpu, or cuda")
    tmp_path = await save_upload(file, suffix, max_bytes=TRANSCRIBE_MAX_BYTES)
    filename = sanitize_upload_filename(file.filename, f"input{suffix}")

    def _work() -> dict:
        try:
            service = TranscriptionService()
            try:
                service.check_available("whisper")
            except TranscriptionError as exc:
                raise JobError(safe_detail(exc)) from exc

            # No progress stream is exposed by the jobs contract, so the
            # backend runs without a callback instead of discarding payloads.
            result = service.transcribe_file(
                str(tmp_path),
                provider_name="whisper",
                model=model,
                language=language,
                device=device,
            )
            content = service.render(result, output_format)
            try:
                with HistoryStore() as store:
                    store.record_transcription_result(
                        result, file_path=filename, file_format=output_format
                    )
            except Exception as exc:
                from ...logging_setup import get_logger

                get_logger("api").warning(
                    "Could not record the transcription (%s)", type(exc).__name__
                )
            payload = TranscriptionResultModel(
                output_content=content,
                output_format=output_format,
                language=result.language,
                processed_items_count=len(result.segments),
                metrics=(
                    result.metrics.to_dict()  # type: ignore[arg-type]
                    if result.metrics is not None
                    else None
                ),
            )
            return payload.model_dump(mode="json")
        except TranscriptionError as exc:
            raise JobError(safe_detail(exc)) from exc
        except (OSError, UnicodeError, ValueError) as exc:
            raise JobError(safe_detail(exc)) from exc
        finally:
            remove_temp(tmp_path)

    try:
        job_id = _jobs_from(request).submit(
            "transcription", _work, on_drop=lambda: remove_temp(tmp_path)
        )
    except Exception:
        remove_temp(tmp_path)
        raise
    return JobCreatedResponse(job_id=job_id, status="queued")
