"""Shared API plumbing: uploads, service factories, error mapping."""

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


def new_service() -> SubtitleService:
    """One service instance per request/job; never shared across threads."""
    return SubtitleService()


def open_history() -> HistoryStore:
    try:
        return HistoryStore()
    except HistoryError as exc:
        raise HTTPException(status_code=500, detail="historial no disponible") from exc


def validate_extension(filename: Optional[str]) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"formato de entrada no soportado: {suffix or '(sin extensión)'}",
        )
    return suffix


def validate_provider(provider: str) -> str:
    """Reject an unknown translation provider as a configuration error.

    Deep-audit L7: an unvalidated provider was accepted, the job ran, every cue
    "failed" with the opaque ``unknown`` error type, and the caller still got a
    completed job. The registry is the single source of truth shared with the
    CLI and the GUI, so this check cannot drift from what would actually run.
    Resolving the provider also surfaces a broken endpoint configuration
    (e.g. a non-HTTPS remote URL) as a 422 instead of a late per-cue failure.
    """
    name = (provider or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="provider es obligatorio")
    try:
        ProviderRegistry.get(name)
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"provider no soportado: {name} "
                f"(disponibles: {', '.join(ProviderRegistry.names())})"
            ),
        ) from exc
    return name


async def save_upload(
    upload: UploadFile, suffix: str, max_bytes: int = MAX_UPLOAD_BYTES
) -> Path:
    """Stream an upload to a temp file with a size cap; caller must delete it."""
    tmp: Optional[Path] = None
    try:
        handle = tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, prefix="srt4u-api-"
        )
        tmp = Path(handle.name)
        received = 0
        while True:
            chunk = await upload.read(65536)
            if not chunk:
                break
            received += len(chunk)
            if received > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"archivo demasiado grande (límite {max_bytes} bytes)",
                )
            handle.write(chunk)
        handle.close()
        return tmp
    except HTTPException:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)
        logger.exception("Fallo al guardar la subida")
        raise HTTPException(
            status_code=500, detail="no se pudo procesar la subida"
        ) from exc


def remove_temp(path: Optional[Path]) -> None:
    if path is not None:
        try:
            os.unlink(path)
        except OSError:
            pass


def safe_detail(exc: Exception, fallback: str = "error interno") -> str:
    """Map known errors to short public messages without exception internals."""
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
        return f"error de transcripción ({error_type})"
    if isinstance(exc, TranslationProviderError):
        messages = {
            ProviderAuthenticationError: "el proveedor rechazó la autenticación",
            ProviderConfigurationError: "configuración del proveedor no válida",
            ProviderNetworkError: "no se pudo conectar con el proveedor",
            ProviderRateLimitError: "el proveedor aplicó un límite de solicitudes",
            ProviderResponseError: "el proveedor devolvió una respuesta no válida",
            ProviderTimeoutError: "el proveedor agotó el tiempo de espera",
            ProviderUnknownError: "falló el proveedor de traducción",
        }
        for error_class, message in messages.items():
            if isinstance(exc, error_class):
                return message
        return "falló el proveedor de traducción"
    return fallback
