"""Whisper transcription backend over ``faster-whisper`` (optional dependency).

Why faster-whisper: pip-installable on Windows/Linux/macOS, fast on CPU via
CTranslate2 (``int8``), optional CUDA acceleration, and no torch-sized
dependency like ``openai-whisper``. The import is lazy so the base product
works without it; absence surfaces as ``TranscriptionNotInstalledError``.

Privacy: fully local inference, no network calls besides the one-time model
download from Hugging Face (announced to the user before running).
"""

import os
import threading
import time
from typing import List, Optional

from ..logging_setup import get_logger
from .config_service import ConfigService
from .transcription_models import (
    TranscriptionMetrics,
    TranscriptionResult,
    TranscriptionSegment,
)
from .transcription_providers import (
    ProgressCallback,
    TranscriptionCancelledError,
    TranscriptionConfig,
    TranscriptionError,
    TranscriptionFFmpegError,
    TranscriptionInvalidFileError,
    TranscriptionMemoryError,
    TranscriptionModelError,
    TranscriptionNotInstalledError,
    TranscriptionProvider,
    TranscriptionRegistry,
    TranscriptionUnknownError,
)

logger = get_logger("transcription")

INSTALL_HINT = "transcripción no disponible: instala el extra con python -m pip install '.[transcription]'"

#: Model -> (approx. download size, short description). Sizes are indicative
#: for the default quantized checkpoints and are shown before any download.
WHISPER_MODELS = {
    "tiny": ("~75 MB", "mínimo, rápido, calidad baja"),
    "base": ("~145 MB", "ligero, calidad aceptable"),
    "small": ("~465 MB", "equilibrio recomendado"),
    "medium": ("~1.5 GB", "mejor calidad, más lento"),
    "large-v3": ("~3 GB", "máxima calidad, lento, más RAM"),
    "turbo": ("~1.6 GB", "rápido con buena calidad"),
}


def _load_faster_whisper():
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]

        return WhisperModel
    except ImportError:
        return None


class WhisperProvider(TranscriptionProvider):
    """Local Whisper transcription via faster-whisper."""

    name = "whisper"

    def __init__(self, config_service: Optional[ConfigService] = None):
        self.config_service = config_service

    def is_available(self) -> bool:
        return _load_faster_whisper() is not None

    def supported_models(self) -> List[str]:
        return list(WHISPER_MODELS)

    @staticmethod
    def model_info(model: str) -> str:
        size, description = WHISPER_MODELS.get(model, ("desconocido", "modelo"))
        return f"'{model}' ({size}, {description})"

    def transcribe(
        self,
        media_path: str,
        config: TranscriptionConfig,
        *,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> TranscriptionResult:
        WhisperModel = _load_faster_whisper()
        if WhisperModel is None:
            raise TranscriptionNotInstalledError(INSTALL_HINT)
        if not media_path or not os.path.isfile(media_path):
            raise TranscriptionInvalidFileError(
                f"archivo multimedia no encontrado: {media_path or '(vacío)'}"
            )
        if config.model not in WHISPER_MODELS:
            raise TranscriptionModelError(
                f"modelo no soportado: {config.model} "
                f"(soportados: {', '.join(WHISPER_MODELS)})"
            )
        if cancel_event is not None and cancel_event.is_set():
            raise TranscriptionCancelledError("transcripción cancelada")

        device = self._resolve_device(config.device)
        size, _ = WHISPER_MODELS[config.model]
        logger.info(
            "Transcribiendo '%s' con whisper/%s en %s "
            "(el modelo, %s, se descarga una vez si no está en caché)",
            os.path.basename(media_path),
            config.model,
            device,
            size,
        )
        started = time.perf_counter()
        try:
            model = WhisperModel(
                config.model,
                device=device,
                compute_type="int8" if device == "cpu" else "float16",
                download_root=os.environ.get("SRT4U_WHISPER_MODEL_DIR") or None,
            )
        except Exception as exc:
            raise _normalize_error(exc, config.model) from exc
        try:
            options = {
                "language": config.normalized_language(),
                "task": "transcribe",
                "vad_filter": config.vad_filter,
            }
            if config.beam_size is not None:
                options["beam_size"] = config.beam_size
            if config.temperature is not None:
                options["temperature"] = config.temperature
            raw_segments, info = model.transcribe(media_path, **options)
            language = getattr(info, "language", None) or (
                config.normalized_language() or "auto"
            )
            media_duration_ms = _optional_ms(getattr(info, "duration", None))
            segments: List[TranscriptionSegment] = []
            for position, raw in enumerate(raw_segments, 1):
                if cancel_event is not None and cancel_event.is_set():
                    raise TranscriptionCancelledError("transcripción cancelada")
                text = (getattr(raw, "text", "") or "").strip()
                if not text:
                    continue
                start_ms = int(float(getattr(raw, "start", 0.0)) * 1000)
                end_ms = int(float(getattr(raw, "end", 0.0)) * 1000)
                segments.append(
                    TranscriptionSegment(
                        index=position,
                        start_ms=max(0, start_ms),
                        end_ms=end_ms,
                        text=text,
                    )
                )
                if progress_callback is not None:
                    payload: dict = {
                        "segments": len(segments),
                        "end_ms": end_ms,
                    }
                    if media_duration_ms:
                        payload["ratio"] = min(1.0, end_ms / media_duration_ms)
                    progress_callback("transcribing", payload)
        except TranscriptionError:
            raise
        except Exception as exc:
            raise _normalize_error(exc, config.model) from exc
        processing_ms = int((time.perf_counter() - started) * 1000)
        metrics = TranscriptionMetrics.build(
            provider=self.name,
            model=config.model,
            source_language=language,
            segments=segments,
            media_duration_ms=media_duration_ms,
            processing_duration_ms=processing_ms,
            device=device,
        )
        return TranscriptionResult(
            segments=segments,
            language=language,
            duration_ms=media_duration_ms,
            model=config.model,
            provider=self.name,
            processing_time_ms=processing_ms,
            success=True,
            metrics=metrics,
            metadata={"device": device},
        )

    @staticmethod
    def _resolve_device(device: str) -> str:
        value = (device or "auto").strip().casefold()
        if value in {"cpu", "cuda"}:
            return value
        if value != "auto":
            raise TranscriptionError(
                f"dispositivo no soportado: {device} (usa auto, cpu o cuda)"
            )
        WhisperModel = _load_faster_whisper()
        if WhisperModel is not None:
            try:
                import ctranslate2  # type: ignore[import-not-found]

                if ctranslate2.get_cuda_device_count() > 0:
                    return "cuda"
            except Exception:
                pass
        return "cpu"


def _optional_ms(seconds: object) -> Optional[int]:
    try:
        value = float(seconds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return int(value * 1000)


def _normalize_error(exc: Exception, model: str) -> TranscriptionError:
    if isinstance(exc, TranscriptionError):
        return exc
    message = str(exc)
    lowered = message.casefold()
    if "ffmpeg" in lowered or "ffprobe" in lowered:
        return TranscriptionFFmpegError(
            "FFmpeg no disponible o no pudo leer el archivo "
            "(instala FFmpeg y reintenta)"
        )
    if (
        "out of memory" in lowered
        or "memory" in lowered
        and ("cuda" in lowered or "alloc" in lowered)
    ):
        return TranscriptionMemoryError(
            f"memoria insuficiente para el modelo '{model}'; "
            "prueba con un modelo menor (tiny/base/small) o cierra aplicaciones"
        )
    if "no such file" in lowered or "not found" in lowered and "model" not in lowered:
        return TranscriptionInvalidFileError("archivo multimedia inválido o ilegible")
    if "model" in lowered and (
        "not found" in lowered
        or "download" in lowered
        or "401" in lowered
        or "403" in lowered
    ):
        return TranscriptionModelError(
            f"modelo '{model}' no disponible "
            f"(soportados: {', '.join(WHISPER_MODELS)}); "
            "revisa tu conexión la primera vez, el modelo se descarga una vez"
        )
    logger.warning("Whisper falló (%s)", type(exc).__name__)
    return TranscriptionUnknownError(
        f"whisper: error inesperado ({type(exc).__name__})"
    )


TranscriptionRegistry.register("whisper", WhisperProvider)
