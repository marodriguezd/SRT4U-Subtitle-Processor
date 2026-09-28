"""Transcription provider contract, normalized errors, and registry.

Mirrors ``translation_providers``: the domain depends only on this ABC, never
on a concrete transcription library. Concrete backends live in their own
modules (e.g. ``transcription_whisper``) and register here.
"""

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..logging_setup import get_logger
from .config_service import ConfigService
from .transcription_models import TranscriptionResult

logger = get_logger("transcription")


class TranscriptionError(Exception):
    """Base error for transcription failures; never contains media content."""

    error_type = "unknown"
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)


class TranscriptionNotInstalledError(TranscriptionError):
    error_type = "provider_not_installed"


class TranscriptionModelError(TranscriptionError):
    error_type = "model_unavailable"


class TranscriptionInvalidFileError(TranscriptionError):
    error_type = "invalid_file"


class TranscriptionFFmpegError(TranscriptionError):
    error_type = "ffmpeg_unavailable"


class TranscriptionFormatError(TranscriptionError):
    error_type = "unsupported_format"


class TranscriptionMemoryError(TranscriptionError):
    error_type = "out_of_memory"
    retryable = False


class TranscriptionCancelledError(TranscriptionError):
    error_type = "cancelled"


class TranscriptionUnknownError(TranscriptionError):
    error_type = "unknown"


@dataclass
class TranscriptionConfig:
    """Small, backend-agnostic transcription settings.

    ``language`` uses ``"auto"`` for backend detection. Optional fields stay
    ``None`` unless the caller sets them; backends apply their own defaults.
    """

    model: str = "small"
    language: str = "auto"
    device: str = "auto"
    beam_size: Optional[int] = None
    temperature: Optional[float] = None
    vad_filter: bool = False

    def normalized_language(self) -> Optional[str]:
        value = (self.language or "").strip().casefold()
        if not value or value == "auto":
            return None
        return value


ProgressCallback = Callable[[str, object], None]


class TranscriptionProvider(ABC):
    """Backend-independent transcription contract."""

    name = "provider"

    @abstractmethod
    def is_available(self) -> bool:
        """True when the backend library (and its binaries) can run here."""

    @abstractmethod
    def supported_models(self) -> List[str]:
        """Model identifiers accepted by ``transcribe``."""

    @abstractmethod
    def transcribe(
        self,
        media_path: str,
        config: TranscriptionConfig,
        *,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> TranscriptionResult:
        """Transcribe media, raising a normalized ``TranscriptionError``."""


class TranscriptionRegistry:
    """Small extensible registry; mirrors ``ProviderRegistry``."""

    _factories: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, factory, *, aliases=(), replace: bool = False) -> None:
        if not callable(factory):
            raise TypeError("la factory de transcripción debe ser invocable")
        names = (name, *aliases)
        normalized = tuple(cls._normalize(value) for value in names)
        if any(not value for value in normalized):
            raise TranscriptionError("los nombres y alias no pueden estar vacíos")
        if any(value in cls._factories for value in normalized) and not replace:
            raise ValueError(f"provider de transcripción ya registrado: {name}")
        for value in normalized:
            cls._factories[value] = factory

    @classmethod
    def get(cls, name: str, config_service: Optional[ConfigService] = None):
        normalized = cls._normalize(name)
        try:
            factory = cls._factories[normalized]
        except KeyError as exc:
            raise TranscriptionError(
                f"provider de transcripción no soportado: {name}"
            ) from exc
        provider = factory(config_service=config_service)
        if not isinstance(provider, TranscriptionProvider):
            raise TranscriptionError(
                f"la factory '{name}' no devolvió un TranscriptionProvider válido"
            )
        return provider

    @classmethod
    def names(cls):
        return tuple(sorted(cls._factories))

    @staticmethod
    def _normalize(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise TranscriptionError(
                "el nombre del provider de transcripción es obligatorio"
            )
        return name.strip().casefold()
