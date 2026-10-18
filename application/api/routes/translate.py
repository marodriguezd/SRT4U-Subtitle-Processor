"""Translate/process endpoints: slow provider work runs as local jobs."""

from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..deps import (
    new_service,
    remove_temp,
    safe_detail,
    sanitize_upload_filename,
    save_upload,
    validate_extension,
    validate_provider,
)
from ..jobs import JobError, JobManager
from ..schemas import JobCreatedResponse, ProcessResultModel, TranslationResultModel
from ...services.history_store import record_result_safely
from ...services.subtitle_service import (
    ProcessingResult,
    ProcessingStats,
    read_subtitle_file,
)
from ...services.translation_service import TranslationService

router = APIRouter(tags=["translate"])

_translate_note = (
    "Translation can take time with remote providers: queues a local job "
    "polled at /jobs/{id}. API keys and provider secrets are never exposed."
)


def _jobs_from(request: Request) -> JobManager:
    return request.app.state.jobs


def _stats_payload(stats: ProcessingStats) -> dict:
    """Map ``ProcessingStats`` onto the served stats contract (B2).

    The previous code passed ``stats.__dict__`` to a model that declared the
    *analytics* field names, so pydantic dropped ``total_lines``,
    ``deleted_lines`` and ``elapsed_time`` and left ``lines_removed`` /
    ``processing_time_seconds`` at their zero defaults. The mapping is now
    explicit, and the two historical aliases carry the real values.
    """
    return {
        "total_lines": stats.total_lines,
        "deleted_lines": stats.deleted_lines,
        "processed_items_count": stats.processed_items_count,
        "elapsed_time": stats.elapsed_time,
        "translation_failures": stats.translation_failures,
        "parse_issues": stats.parse_issues,
        "processing_time_seconds": stats.elapsed_time,
        "lines_removed": stats.deleted_lines,
    }


def _empty_metrics(provider: str, target_language: str) -> dict:
    return {
        "provider": provider,
        "model": None,
        "source_language": "auto",
        "target_language": target_language,
        "success": False,
        "error_type": "unknown",
    }


@router.post(
    "/translate",
    response_model=JobCreatedResponse,
    status_code=202,
    summary="Translate a subtitle file (job)",
    description=_translate_note,
)
async def translate(
    request: Request,
    file: UploadFile = File(description="Subtitle file (.srt/.vtt/.ass/.ssa/.txt)"),  # noqa: B008
    source_language: Annotated[str, Form(description="Source language code")] = "auto",  # noqa: B008
    target_language: Annotated[str, Form(description="Target language code")] = "es",  # noqa: B008
    provider: Annotated[
        str, Form(description="google, deepl, openai, ollama, llm")
    ] = "google",  # noqa: B008
    max_retries: Annotated[
        int, Form(description="Retry attempts on transient errors")
    ] = 0,  # noqa: B008
    no_fallback: Annotated[bool, Form(description="Disable fallback")] = False,  # noqa: B008
) -> JobCreatedResponse:
    suffix = validate_extension(file.filename)
    provider = validate_provider(provider)
    if not target_language or not target_language.strip():
        raise HTTPException(status_code=422, detail="target_language is required")
    if max_retries < 0 or max_retries > 10:
        raise HTTPException(
            status_code=422, detail="max_retries must be between 0 and 10"
        )
    tmp_path = await save_upload(file, suffix)
    filename = sanitize_upload_filename(file.filename, f"input{suffix}")

    def _work() -> dict:
        try:
            # Same decoding policy as the CLI/GUI: BOM, UTF-16 and CP1252 are
            # detected instead of replaced with U+FFFD.
            content = read_subtitle_file(str(tmp_path))
            service = new_service()
            service.translation_service = TranslationService(
                max_retries=max_retries,
                fallbacks={} if no_fallback else None,
            )
            file_format = service.detect_format(content, f"input{suffix}")
            items = service.parse_subtitles(content, file_format)
            translated = service.translate_subtitles(
                items=items,
                target_language=target_language,
                source_language=source_language,
                engine=provider,
                parallel=False,
            )
            metrics = service.last_translation_metrics
            record_result_safely(
                ProcessingResult(
                    stats=ProcessingStats(
                        processed_items_count=len(items),
                        translation_failures=service.last_translation_failures,
                    ),
                    processed_items=translated,
                    translation_metrics=metrics,
                ),
                operation="process",
                file_path=filename,
                file_format=file_format,
                source_language=source_language,
                target_language=target_language,
                engine=provider,
            )
            payload = TranslationResultModel(
                text="\n".join(item.text for item in translated),
                metrics=(
                    metrics.to_dict()
                    if metrics is not None
                    else _empty_metrics(provider, target_language)  # type: ignore[arg-type]
                ),
            )
            return payload.model_dump(mode="json")
        except (OSError, UnicodeError, ValueError) as exc:
            raise JobError(safe_detail(exc)) from exc
        finally:
            remove_temp(tmp_path)

    try:
        job_id = _jobs_from(request).submit(
            "translate", _work, on_drop=lambda: remove_temp(tmp_path)
        )
    except Exception:
        remove_temp(tmp_path)
        raise
    return JobCreatedResponse(job_id=job_id, status="queued")


@router.post(
    "/process",
    response_model=JobCreatedResponse,
    status_code=202,
    summary="Process a file: clean + translate + QA (job)",
    description="Reuses `SubtitleService.process_subtitles` (read → analyze → "
    "clean → translate → format) and records history. Full outcome "
    "polled at /jobs/{id}.",
)
async def process(
    request: Request,
    file: UploadFile = File(description="Subtitle file (.srt/.vtt/.ass/.ssa/.txt)"),  # noqa: B008
    clean: Annotated[bool, Form(description="Clean promotional and spam lines")] = True,  # noqa: B008
    translate: Annotated[bool, Form(description="Translate subtitles")] = False,  # noqa: B008
    source_language: Annotated[str, Form(description="Source language code")] = "auto",  # noqa: B008
    target_language: Annotated[
        Optional[str], Form(description="Target language code")
    ] = None,  # noqa: B008
    provider: Annotated[
        str, Form(description="google, deepl, openai, ollama, llm")
    ] = "google",  # noqa: B008
    target_format: Annotated[
        Optional[str], Form(description="srt, vtt, ass, ssa, txt")
    ] = None,  # noqa: B008
    max_retries: Annotated[
        int, Form(description="Retry attempts on transient errors")
    ] = 0,  # noqa: B008
    no_fallback: Annotated[bool, Form(description="Disable fallback")] = False,  # noqa: B008
) -> JobCreatedResponse:
    suffix = validate_extension(file.filename)
    provider = validate_provider(provider)
    if translate and not (target_language or "").strip():
        raise HTTPException(
            status_code=422, detail="target_language is required when translating"
        )
    if target_format is not None and target_format not in {
        "srt",
        "vtt",
        "ass",
        "ssa",
        "txt",
    }:
        raise HTTPException(status_code=422, detail="target_format not supported")
    if max_retries < 0 or max_retries > 10:
        raise HTTPException(
            status_code=422, detail="max_retries must be between 0 and 10"
        )
    tmp_path = await save_upload(file, suffix)
    filename = sanitize_upload_filename(file.filename, f"input{suffix}")

    def _work() -> dict:
        try:
            service = new_service()
            service.translation_service = TranslationService(
                max_retries=max_retries,
                fallbacks={} if no_fallback else None,
            )
            result = service.process_subtitles(
                file_path=str(tmp_path),
                do_clean=clean,
                do_translate=translate,
                target_language=target_language,
                source_language=source_language,
                engine=provider,
                target_format=target_format,
                parallel=False,
            )
            record_result_safely(
                result,
                operation="process",
                file_path=filename,
                file_format=target_format or tmp_path.suffix.lstrip("."),
                source_language=source_language,
                target_language=target_language,
                engine=provider,
            )
            payload = ProcessResultModel(
                output_content=result.output_content,
                output_format=target_format or tmp_path.suffix.lstrip("."),
                stats=_stats_payload(result.stats),
                processed_items_count=result.stats.processed_items_count,
                translation_metrics=(
                    result.translation_metrics.to_dict()
                    if result.translation_metrics is not None
                    else None
                ),
                qa=result.qa_report.to_dict() if result.qa_report is not None else None,  # type: ignore[arg-type]
            )
            data = payload.model_dump(mode="json")
            # P1: parser findings ride along as a top-level advisory list
            # (kind/reason/line/snippet) so API clients can warn their users.
            # ProcessResultModel declares the field, so the served OpenAPI
            # contract matches this runtime payload.
            data["parse_issues"] = [
                issue.to_dict() for issue in getattr(result, "parse_issues", [])
            ]
            return data
        except (OSError, UnicodeError, ValueError) as exc:
            raise JobError(safe_detail(exc)) from exc
        finally:
            remove_temp(tmp_path)

    try:
        job_id = _jobs_from(request).submit(
            "process", _work, on_drop=lambda: remove_temp(tmp_path)
        )
    except Exception:
        remove_temp(tmp_path)
        raise
    return JobCreatedResponse(job_id=job_id, status="queued")
