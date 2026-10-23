"""Shared API plumbing: uploads, service factories, error mapping."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from ..logging_setup import get_logger
from ..services.history_store import HistoryError, HistoryStore
from ..services.subtitle_service import SubtitleService
from ..services.translation_providers import (
    ProviderConfigurationError,
    ProviderRegistry,
)

logger = get_logger("api")

SUPPORTED_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".txt"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

#: Coalesce upload chunks up to this size: one blocking write per chunk instead
#: of a thread hop per 64 KiB read.
_UPLOAD_WRITE_BATCH = 1024 * 1024


def new_service() -> SubtitleService:
    """One service instance per request/job; never shared across threads."""
    return SubtitleService()


def open_history() -> HistoryStore:
    try:
        return HistoryStore()
    except HistoryError as exc:
        raise HTTPException(status_code=500, detail="history unavailable") from exc


def validate_extension(filename: Optional[str]) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported input format: {suffix or '(no extension)'}",
        )
    return suffix


def validate_provider(provider: str) -> str:
    """Reject an unknown translation provider as a configuration error.

    L7: the registry shared with the CLI and GUI is the single source of truth,
    and resolving here also surfaces a broken endpoint as 422, not a late
    per-cue failure.
    """
    name = (provider or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="provider is required")
    try:
        ProviderRegistry.get(name)
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"unsupported provider: {name} "
                f"(available: {', '.join(ProviderRegistry.names())})"
            ),
        ) from exc
    return name


def sanitize_upload_filename(
    filename: Optional[str], default: str = "upload.tmp"
) -> str:
    """Strip path traversal and Windows/POSIX directory components."""
    if not filename:
        return default
    cleaned = filename.replace("\\", "/").rstrip("/").split("/")[-1].strip()
    if not cleaned or cleaned in (".", ".."):
        return default
    return cleaned


async def save_upload(
    upload: UploadFile, suffix: str, max_bytes: int = MAX_UPLOAD_BYTES
) -> Path:
    """Stream an upload to a temp file with a size cap; caller must delete it."""
    tmp: Optional[Path] = None
    handle = None
    success = False

    def cleanup() -> None:
        # Close before unlinking: Windows does not allow deleting an open file.
        # Cleanup must not mask the original upload/HTTP error.
        nonlocal handle
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
            handle = None
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove a temporary upload file")

    try:
        handle = tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, prefix="srt4u-api-"
        )
        tmp = Path(handle.name)
        received = 0
        pending = bytearray()
        while True:
            chunk = await upload.read(65536)
            if not chunk:
                break
            received += len(chunk)
            if received > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"file too large (limit {max_bytes} bytes)",
                )
            pending.extend(chunk)
            if len(pending) >= _UPLOAD_WRITE_BATCH:
                await asyncio.to_thread(handle.write, bytes(pending))
                pending.clear()
        if pending:
            await asyncio.to_thread(handle.write, bytes(pending))
        handle.close()
        handle = None
        success = True
        return tmp
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to save the upload")
        raise HTTPException(
            status_code=500, detail="could not process the upload"
        ) from exc
    finally:
        if not success:
            cleanup()


def remove_temp(path: Optional[Path]) -> None:
    if path is not None:
        try:
            os.unlink(path)
        except OSError:
            pass


def safe_detail(exc: Exception, fallback: str = "internal error") -> str:
    """Map known errors to short public messages without exception internals."""
    from ..services.media_pipeline import PipelineConfigError
    from ..services.transcription_providers import TranscriptionError
    from ..services.transcription_whisper import INSTALL_HINT
    from ..services.translation_providers import (
        ProviderAuthenticationError,
        ProviderConfigurationError,
        ProviderNetworkError,
        ProviderRateLimitError,
        ProviderResponseError,
        ProviderTimeoutError,
        ProviderUnknownError,
        TranslationProviderError,
    )

    if isinstance(exc, PipelineConfigError):
        # D5: these messages come from ``PipelineConfig.validate`` with the
        # caller's own parameters, so they never leak server internals.
        message = str(exc).strip()
        return message or fallback
    if isinstance(exc, TranscriptionError):
        message = str(exc).strip()
        if INSTALL_HINT in message:
            return INSTALL_HINT
        error_types = {
            "provider_not_installed",
            "model_unavailable",
            "invalid_file",
            "ffmpeg_unavailable",
            "unsupported_format",
            "out_of_memory",
            "cancelled",
            "unknown",
        }
        error_type = exc.error_type if exc.error_type in error_types else "unknown"
        return f"transcription error ({error_type})"
    if isinstance(exc, TranslationProviderError):
        messages = {
            ProviderAuthenticationError: "the provider rejected authentication",
            ProviderConfigurationError: "invalid provider configuration",
            ProviderNetworkError: "could not connect to the provider",
            ProviderRateLimitError: "the provider applied a rate limit",
            ProviderResponseError: "the provider returned an invalid response",
            ProviderTimeoutError: "the provider timed out",
            ProviderUnknownError: "the translation provider failed",
        }
        for error_class, message in messages.items():
            if isinstance(exc, error_class):
                return message
        return "the translation provider failed"
    return fallback
