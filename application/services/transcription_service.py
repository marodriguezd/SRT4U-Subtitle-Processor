"""Transcription coordinator shared by the GUI, CLI, and API.

Validates media inputs, resolves the backend through ``TranscriptionRegistry``,
and converts results to ``SubtitleItem``/SRT/VTT via ``SubtitleService`` so
transcription flows into Analytics, QA, cleaning, translation, and burn-in.
"""

import os
import threading
from typing import List, Optional

from ..logging_setup import get_logger
from .config_service import ConfigService
from .subtitle_service import SubtitleItem, SubtitleService
from .transcription_models import TranscriptionResult
from .transcription_providers import (
    ProgressCallback,
    TranscriptionConfig,
    TranscriptionError,
    TranscriptionFormatError,
    TranscriptionInvalidFileError,
    TranscriptionRegistry,
)

logger = get_logger("transcription")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpg", ".mpeg"}
AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".ogg",
    ".oga",
    ".opus",
    ".flac",
    ".aac",
    ".wma",
}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

PROVIDER_ENV_VAR = "SRT4U_TRANSCRIPTION_PROVIDER"
DEFAULT_PROVIDER = "whisper"


class TranscriptionService:
    """Backend-agnostic transcription entry point (no heavy imports here)."""

    def __init__(
        self,
        config_service: Optional[ConfigService] = None,
        subtitle_service: Optional[SubtitleService] = None,
    ):
        self.config_service = config_service
        self.subtitle_service = subtitle_service or SubtitleService()

    @staticmethod
    def default_provider() -> str:
        return (
            os.environ.get(PROVIDER_ENV_VAR, DEFAULT_PROVIDER).strip()
            or DEFAULT_PROVIDER
        )

    @staticmethod
    def validate_media(media_path: str) -> str:
        """Return the lowercase extension or raise a normalized error."""
        if not media_path or not os.path.isfile(media_path):
            raise TranscriptionInvalidFileError(
                f"archivo multimedia no encontrado: {media_path or '(vacío)'}"
            )
        suffix = os.path.splitext(media_path)[1].lower()
        if suffix not in MEDIA_EXTENSIONS:
            raise TranscriptionFormatError(
                f"formato multimedia no soportado: {suffix or '(sin extensión)'} "
                f"(soportados: {', '.join(sorted(MEDIA_EXTENSIONS))})"
            )
        return suffix

    def provider_names(self) -> tuple:
        return TranscriptionRegistry.names()

    def check_available(self, provider_name: Optional[str] = None) -> str:
        """Resolve the provider and fail clearly when its backend is missing."""
        name = (provider_name or self.default_provider()).strip() or DEFAULT_PROVIDER
        provider = TranscriptionRegistry.get(name, self.config_service)
        if not provider.is_available():
            from .transcription_whisper import INSTALL_HINT

            raise TranscriptionError(
                f"provider '{name}' no disponible: {INSTALL_HINT}"
                if name == "whisper"
                else f"provider '{name}' no disponible en este equipo"
            )
        return name

    def transcribe_file(
        self,
        media_path: str,
        *,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        device: Optional[str] = None,
        beam_size: Optional[int] = None,
        temperature: Optional[float] = None,
        vad_filter: bool = False,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> TranscriptionResult:
        self.validate_media(media_path)
        name = (provider_name or self.default_provider()).strip() or DEFAULT_PROVIDER
        provider = TranscriptionRegistry.get(name, self.config_service)
        config = TranscriptionConfig(
            model=model or self._default_model(),
            language=language or "auto",
            device=device or "auto",
            beam_size=beam_size,
            temperature=temperature,
            vad_filter=vad_filter,
        )
        return provider.transcribe(
            media_path,
            config,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def to_subtitle_items(self, result: TranscriptionResult) -> List[SubtitleItem]:
        return result.to_subtitle_items()

    def render(self, result: TranscriptionResult, output_format: str = "srt") -> str:
        """Format transcription cues reusing the existing subtitle formatters."""
        fmt = (output_format or "srt").lower().lstrip(".")
        if fmt not in {"srt", "vtt"}:
            raise TranscriptionError(
                f"formato de salida no soportado: {output_format} (usa srt o vtt)"
            )
        return self.subtitle_service.format_output(self.to_subtitle_items(result), fmt)

    def _default_model(self) -> str:
        if self.config_service is not None:
            try:
                value = str(
                    self.config_service.get("transcription_model", "small")
                ).strip()
                if value:
                    return value
            except Exception:
                pass
        return "small"
