"""Shared API plumbing: uploads, service factories, error mapping."""

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from ..logging_setup import get_logger
from ..services.history_store import HistoryError, HistoryStore
from ..services.subtitle_service import SubtitleService

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
    """Short, non-sensitive error text for HTTP responses."""
    text = str(exc).strip()
    if not text or "Traceback" in text:
        return fallback
    return text[:300]
