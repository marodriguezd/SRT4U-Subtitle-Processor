"""End-to-end audiovisual pipeline reusing the existing SRT4U services.

MEDIA/SUBTITLE
→ transcription (TranscriptionService) → cleaning (SubtitleService)
→ analytics → QA → optional translation (TranslationService via
SubtitleService.translate_subtitles) → final analytics → final QA
→ export (SubtitleService.format_output) → optional burn-in (FFmpeg,
same recipe as VideoBurnerService).

No domain logic is duplicated: every stage delegates to the service that
already owns it. The pipeline only orchestrates, times, records, and
serializes. Cancellation is cooperative between stages (plus inside
transcription and burn-in); translation inherits the existing
never-raise/keep-original behavior of ``translate_subtitles``.
"""

import os
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..logging_setup import get_logger
from .config_service import ConfigService
from .subtitle_service import SubtitleItem, SubtitleService
from .transcription_models import TranscriptionResult
from .transcription_providers import (
    TranscriptionCancelledError,
    TranscriptionError,
)
from .transcription_service import (
    MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
    TranscriptionService,
)
from .translation_service import TranslationService

logger = get_logger("pipeline")

SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".txt"}
EXPORT_FORMATS = ("srt", "vtt")

STAGE_TRANSCRIBE = "transcription"
STAGE_PARSE = "parse"
STAGE_CLEAN = "cleaning"
STAGE_ANALYZE = "analytics"
STAGE_QA = "qa"
STAGE_TRANSLATE = "translation"
STAGE_ANALYZE_FINAL = "analytics_final"
STAGE_QA_FINAL = "qa_final"
STAGE_EXPORT = "export"
STAGE_BURN = "burn_in"

STATUS_OK = "ok"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ProgressCallback = Callable[[str, object], None]
BurnRunner = Callable[..., str]


class PipelineConfigError(Exception):
    """Invalid configuration or input; distinct from execution failures."""


class PipelineStageError(Exception):
    """Execution failure bound to a stage, carrying a stable error type."""

    def __init__(self, stage: str, error_type: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.error_type = error_type


@dataclass
class PipelineConfig:
    """Explicit pipeline settings; ``validate`` separates config from run errors."""

    input_media: str
    output_subtitle: Optional[str] = None
    transcription_enabled: bool = True
    transcription_model: str = "small"
    transcription_language: str = "auto"
    transcription_device: str = "auto"
    clean_enabled: bool = True
    qa_enabled: bool = True
    qa_strict: bool = False
    translation_enabled: bool = False
    source_language: str = "auto"
    target_language: Optional[str] = None
    provider: str = "google"
    max_retries: int = 0
    fallback_enabled: bool = True
    output_format: str = "srt"
    burn_in_enabled: bool = False
    output_video: Optional[str] = None

    def validate(self) -> "PipelineConfig":
        source = self.input_media or ""
        if not source or not os.path.isfile(source):
            raise PipelineConfigError(
                f"archivo de entrada no encontrado: {source or '(vacío)'}"
            )
        suffix = os.path.splitext(source)[1].lower()
        if suffix not in MEDIA_EXTENSIONS and suffix not in SUBTITLE_EXTENSIONS:
            raise PipelineConfigError(
                f"extensión de entrada no soportada: {suffix or '(sin extensión)'}"
            )
        is_media = suffix in MEDIA_EXTENSIONS
        if is_media and not self.transcription_enabled:
            raise PipelineConfigError(
                "la entrada es audio/vídeo pero la transcripción está desactivada"
            )
        if self.output_format not in EXPORT_FORMATS:
            raise PipelineConfigError(
                f"formato de salida no soportado: {self.output_format} (usa srt o vtt)"
            )
        if self.translation_enabled and not (self.target_language or "").strip():
            raise PipelineConfigError(
                "target_language es obligatorio cuando la traducción está activada"
            )
        if self.max_retries is None or self.max_retries < 0:
            raise PipelineConfigError("max_retries debe ser un entero no negativo")
        if self.burn_in_enabled:
            if not is_media or suffix not in VIDEO_EXTENSIONS:
                raise PipelineConfigError("el burn-in requiere un vídeo como entrada")
            if not (self.output_video or "").strip():
                raise PipelineConfigError(
                    "output_video es obligatorio cuando el burn-in está activado"
                )
        if self.output_subtitle:
            parent = os.path.dirname(os.path.abspath(self.output_subtitle))
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError as exc:
                raise PipelineConfigError(
                    f"no se pudo crear el directorio de salida: {exc}"
                ) from exc
            if os.path.abspath(self.output_subtitle) == os.path.abspath(source):
                raise PipelineConfigError(
                    "la salida no puede sobrescribir el archivo de entrada"
                )
        return self

    def is_media_input(self) -> bool:
        return os.path.splitext(self.input_media)[1].lower() in MEDIA_EXTENSIONS


@dataclass
class PipelineStage:
    name: str
    status: str = STATUS_SKIPPED
    duration_ms: int = 0
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    """Structured outcome; JSON-safe via ``to_dict`` (no media bytes)."""

    success: bool = False
    cancelled: bool = False
    failed_stage: Optional[str] = None
    stages: List[PipelineStage] = field(default_factory=list)
    transcription_result: Optional[TranscriptionResult] = None
    translation_metrics: Optional[Any] = None
    # Fallos reales de traducción (cues que mantienen el texto original).
    # Nunca debe confundirse con ``translation_metrics.number_of_cues``,
    # que cuenta los cues procesados, no los fallidos.
    translation_failures: int = 0
    analytics_before: Optional[Dict[str, Any]] = None
    qa_before: Optional[Dict[str, Any]] = None
    analytics_after: Optional[Dict[str, Any]] = None
    qa_after: Optional[Dict[str, Any]] = None
    cleaning: Dict[str, Any] = field(default_factory=dict)
    output_content: str = ""
    output_format: str = "srt"
    output_subtitle: Optional[str] = None
    output_video: Optional[str] = None
    total_duration_ms: int = 0
    media_duration_ms: Optional[int] = None
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def stages_completed(self) -> int:
        return sum(1 for stage in self.stages if stage.status == STATUS_OK)

    def to_dict(self) -> Dict[str, Any]:
        metrics = self.translation_metrics
        return {
            "success": self.success,
            "cancelled": self.cancelled,
            "failed_stage": self.failed_stage,
            "stages": [stage.to_dict() for stage in self.stages],
            "stages_completed": self.stages_completed,
            "transcription": (
                self.transcription_result.to_dict()
                if self.transcription_result is not None
                else None
            ),
            "translation_metrics": (metrics.to_dict() if metrics is not None else None),
            "translation_failures": self.translation_failures,
            "analytics_before": self.analytics_before,
            "qa_before": self.qa_before,
            "analytics_after": self.analytics_after,
            "qa_after": self.qa_after,
            "cleaning": dict(self.cleaning),
            "output_content": self.output_content,
            "output_format": self.output_format,
            "output_subtitle": self.output_subtitle,
            "output_video": self.output_video,
            "total_duration_ms": self.total_duration_ms,
            "media_duration_ms": self.media_duration_ms,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class MediaPipeline:
    """Orchestrator; one instance per run (never shared across threads)."""

    def __init__(
        self,
        config_service: Optional[ConfigService] = None,
        transcription_service: Optional[TranscriptionService] = None,
        subtitle_service: Optional[SubtitleService] = None,
        burn_runner: Optional[BurnRunner] = None,
    ):
        self.config_service = config_service
        self.transcription_service = transcription_service or TranscriptionService(
            config_service
        )
        self.subtitle_service = subtitle_service or SubtitleService()
        self.burn_runner: BurnRunner = burn_runner or run_burn_in_sync

    def run(
        self,
        config: PipelineConfig,
        *,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> PipelineResult:
        config.validate()
        result = PipelineResult(output_format=config.output_format)
        started = time.perf_counter()
        items: List[SubtitleItem] = []
        stages = STAGE_ORDER

        def emit(stage: str, payload: object = None) -> None:
            if progress_callback is not None:
                progress_callback(stage, payload if payload is not None else {})

        def check_cancel(stage: str) -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise PipelineStageError(stage, "cancelled", "pipeline cancelada")

        try:
            for stage in stages:
                stage_started = time.perf_counter()
                emit(stage, {"state": "started"})
                try:
                    check_cancel(stage)
                    if not self._is_applicable(stage, config):
                        self._close_stage(
                            result, stage, STATUS_SKIPPED, stage_started, {}
                        )
                        emit(stage, {"state": STATUS_SKIPPED})
                        continue
                    items, detail = self._run_stage(
                        stage, config, result, items, emit, cancel_event
                    )
                except PipelineStageError as exc:
                    self._close_stage(
                        result,
                        stage,
                        STATUS_CANCELLED
                        if exc.error_type == "cancelled"
                        else STATUS_FAILED,
                        stage_started,
                        {"error_type": exc.error_type},
                    )
                    if exc.error_type == "cancelled":
                        result.cancelled = True
                    else:
                        result.failed_stage = exc.stage
                    result.errors.append(
                        {
                            "stage": exc.stage,
                            "error_type": exc.error_type,
                            "message": str(exc),
                        }
                    )
                    emit(stage, {"state": result.stages[-1].status})
                    break
                self._close_stage(result, stage, STATUS_OK, stage_started, detail)
                emit(stage, {"state": STATUS_OK})
            else:
                result.success = True
        finally:
            result.total_duration_ms = int((time.perf_counter() - started) * 1000)
        return result

    @staticmethod
    def _is_applicable(stage: str, config: PipelineConfig) -> bool:
        if stage == STAGE_TRANSCRIBE:
            return config.is_media_input()
        if stage == STAGE_PARSE:
            return not config.is_media_input()
        if stage == STAGE_CLEAN:
            return config.clean_enabled
        if stage in {STAGE_QA, STAGE_QA_FINAL}:
            return config.qa_enabled
        if stage == STAGE_TRANSLATE:
            return config.translation_enabled
        if stage == STAGE_BURN:
            return config.burn_in_enabled
        return True

    def _close_stage(
        self,
        result: PipelineResult,
        stage: str,
        status: str,
        stage_started: float,
        detail: Dict[str, Any],
    ) -> None:
        for existing in result.stages:
            if existing.name == stage:
                existing.status = status
                existing.duration_ms = int((time.perf_counter() - stage_started) * 1000)
                existing.detail.update(detail)
                return
        result.stages.append(
            PipelineStage(
                name=stage,
                status=status,
                duration_ms=int((time.perf_counter() - stage_started) * 1000),
                detail=detail,
            )
        )

    # -- stages -----------------------------------------------------------

    def _run_stage(
        self,
        stage: str,
        config: PipelineConfig,
        result: PipelineResult,
        items: List[SubtitleItem],
        emit: Callable[[str, object], None],
        cancel_event: Optional[threading.Event],
    ) -> tuple:
        if stage == STAGE_TRANSCRIBE:
            return self._stage_transcribe(config, result, emit, cancel_event), {}
        if stage == STAGE_PARSE:
            return self._stage_parse(config, result), {}
        if stage == STAGE_CLEAN:
            return self._stage_clean(config, result, items), dict(result.cleaning)
        if stage == STAGE_ANALYZE:
            analytics, _ = self.subtitle_service.analyze_subtitles(
                items, file_format=config.output_format
            )
            result.analytics_before = analytics.to_dict()
            detail = {"subtitle_count": analytics.content.subtitle_count}
            return items, detail
        if stage == STAGE_QA:
            return self._stage_qa(config, result, items, before=True), {}
        if stage == STAGE_TRANSLATE:
            return (
                self._stage_translate(config, result, items, emit, cancel_event),
                {},
            )
        if stage == STAGE_ANALYZE_FINAL:
            analytics, _ = self.subtitle_service.analyze_subtitles(
                items, file_format=config.output_format
            )
            result.analytics_after = analytics.to_dict()
            detail = {"subtitle_count": analytics.content.subtitle_count}
            return items, detail
        if stage == STAGE_QA_FINAL:
            return self._stage_qa(config, result, items, before=False), {}
        if stage == STAGE_EXPORT:
            return self._stage_export(config, result, items), {
                "output_subtitle": result.output_subtitle
            }
        if stage == STAGE_BURN:
            return self._stage_burn(config, result, items, emit, cancel_event), {
                "output_video": result.output_video
            }
        raise PipelineStageError(stage, "unknown", f"etapa desconocida: {stage}")

    def _stage_transcribe(
        self,
        config: PipelineConfig,
        result: PipelineResult,
        emit: Callable[[str, object], None],
        cancel_event: Optional[threading.Event],
    ) -> List[SubtitleItem]:
        try:
            transcription = self.transcription_service.transcribe_file(
                config.input_media,
                model=config.transcription_model,
                language=config.transcription_language,
                device=config.transcription_device,
                progress_callback=lambda step, payload: emit(STAGE_TRANSCRIBE, payload),
                cancel_event=cancel_event,
            )
        except TranscriptionCancelledError as exc:
            raise PipelineStageError(STAGE_TRANSCRIBE, "cancelled", str(exc)) from exc
        except TranscriptionError as exc:
            raise PipelineStageError(
                STAGE_TRANSCRIBE, exc.error_type, str(exc)
            ) from exc
        result.transcription_result = transcription
        result.media_duration_ms = transcription.duration_ms
        return self.transcription_service.to_subtitle_items(transcription)

    def _stage_parse(
        self, config: PipelineConfig, result: PipelineResult
    ) -> List[SubtitleItem]:
        try:
            with open(config.input_media, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            file_format = self.subtitle_service.detect_format(
                content, config.input_media
            )
            parsed = self.subtitle_service.parse_subtitles(content, file_format)
        except (OSError, UnicodeError, ValueError) as exc:
            raise PipelineStageError(
                STAGE_PARSE, "invalid_file", f"no se pudo leer el subtítulo: {exc}"
            ) from exc
        if not parsed:
            raise PipelineStageError(
                STAGE_PARSE, "invalid_file", "el subtítulo no contiene cues"
            )
        return parsed

    def _stage_clean(
        self,
        config: PipelineConfig,
        result: PipelineResult,
        items: List[SubtitleItem],
    ) -> List[SubtitleItem]:
        cleaned, _total, removed = self.subtitle_service.clean_subtitles(items)
        result.cleaning = {
            "lines_removed": removed,
            "items_before": len(items),
            "items_after": len(cleaned),
        }
        if removed:
            result.warnings.append(f"limpieza: {removed} líneas eliminadas")
        return cleaned

    def _stage_qa(
        self,
        config: PipelineConfig,
        result: PipelineResult,
        items: List[SubtitleItem],
        *,
        before: bool,
    ) -> List[SubtitleItem]:
        stage = STAGE_QA if before else STAGE_QA_FINAL
        report = self.subtitle_service.qa_subtitles(
            items, file_format=config.output_format
        )
        payload = report.to_dict()
        if before:
            result.qa_before = payload
        else:
            result.qa_after = payload
        gate = report.strict_passed if config.qa_strict else report.passed
        if not gate:
            if config.qa_strict:
                raise PipelineStageError(
                    stage,
                    "qa_failed",
                    f"QA estricto: {report.error_count} errores, "
                    f"{report.warning_count} avisos",
                )
            result.warnings.append(
                f"QA: {report.error_count} errores, {report.warning_count} avisos"
            )
        return items

    def _stage_translate(
        self,
        config: PipelineConfig,
        result: PipelineResult,
        items: List[SubtitleItem],
        emit: Callable[[str, object], None],
        cancel_event: Optional[threading.Event],
    ) -> List[SubtitleItem]:
        translation_service = TranslationService(
            self.config_service,
            max_retries=config.max_retries,
            fallbacks=None if config.fallback_enabled else {},
        )
        worker = SubtitleService(
            translation_service, batch_size=self.subtitle_service.batch_size
        )

        def _progress(step: str, payload: object) -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise TranscriptionCancelledError("pipeline cancelada")
            emit(STAGE_TRANSLATE, payload)

        try:
            translated = worker.translate_subtitles(
                items=items,
                target_language=config.target_language or "",
                source_language=config.source_language,
                engine=config.provider,
                parallel=False,
                progress_callback=_progress,
            )
        except TranscriptionCancelledError as exc:
            raise PipelineStageError(STAGE_TRANSLATE, "cancelled", str(exc)) from exc
        metrics = worker.last_translation_metrics
        result.translation_metrics = metrics
        failures = worker.last_translation_failures
        result.translation_failures = failures or 0
        if metrics is not None and not metrics.success:
            raise PipelineStageError(
                STAGE_TRANSLATE,
                metrics.error_type or "translation_error",
                f"traducción fallida ({metrics.error_type or 'unknown'})",
            )
        if failures:
            result.warnings.append(
                f"traducción: {failures} cues mantienen el texto original"
            )
        return translated

    def _stage_export(
        self,
        config: PipelineConfig,
        result: PipelineResult,
        items: List[SubtitleItem],
    ) -> List[SubtitleItem]:
        if not items:
            raise PipelineStageError(
                STAGE_EXPORT, "export_error", "nada que exportar (0 cues)"
            )
        try:
            content = self.subtitle_service.format_output(items, config.output_format)
        except (ValueError, TypeError) as exc:
            raise PipelineStageError(
                STAGE_EXPORT, "export_error", f"no se pudo formatear: {exc}"
            ) from exc
        destination = config.output_subtitle or self._default_output(config)
        try:
            parent = os.path.dirname(os.path.abspath(destination))
            os.makedirs(parent, exist_ok=True)
            with open(destination, "w", encoding="utf-8", newline="") as f:
                f.write(content)
        except OSError as exc:
            raise PipelineStageError(
                STAGE_EXPORT, "export_error", f"no se pudo escribir: {exc}"
            ) from exc
        result.output_content = content
        result.output_subtitle = destination
        return items

    def _stage_burn(
        self,
        config: PipelineConfig,
        result: PipelineResult,
        items: List[SubtitleItem],
        emit: Callable[[str, object], None],
        cancel_event: Optional[threading.Event],
    ) -> List[SubtitleItem]:
        try:
            output = self.burn_runner(
                config.input_media,
                items,
                config.output_video or "",
                progress_callback=lambda payload: emit(STAGE_BURN, payload),
                cancel_event=cancel_event,
            )
        except TranscriptionCancelledError as exc:
            raise PipelineStageError(STAGE_BURN, "cancelled", str(exc)) from exc
        except PipelineStageError:
            raise
        except Exception as exc:
            raise PipelineStageError(
                STAGE_BURN, "burn_in_error", f"burn-in fallido: {exc}"
            ) from exc
        result.output_video = output
        return items

    @staticmethod
    def _default_output(config: PipelineConfig) -> str:
        base, _ = os.path.splitext(config.input_media)
        return f"{base}_pipeline.{config.output_format}"


STAGE_ORDER = (
    STAGE_TRANSCRIBE,
    STAGE_PARSE,
    STAGE_CLEAN,
    STAGE_ANALYZE,
    STAGE_QA,
    STAGE_TRANSLATE,
    STAGE_ANALYZE_FINAL,
    STAGE_QA_FINAL,
    STAGE_EXPORT,
    STAGE_BURN,
)


def run_burn_in_sync(
    video_path: str,
    items: List[SubtitleItem],
    output_path: str,
    *,
    progress_callback: Optional[Callable[[object], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> str:
    """Headless burn-in reusing VideoBurnerService detection, ASS, and flags.

    The Qt-bound ``BurnInWorker`` cannot run in headless contexts; this uses
    the same binary lookup, ASS generation, and ffmpeg command. Importing the
    burner requires PyQt6 (desktop extra): absence surfaces as a clear error.
    """
    try:
        from .video_burner_service import BurnInOptions, VideoBurnerService
    except ImportError as exc:
        raise PipelineStageError(
            STAGE_BURN, "burn_in_error", "burn-in requiere el extra desktop (PyQt6)"
        ) from exc
    ffmpeg_bin = VideoBurnerService.get_ffmpeg_path()
    if not ffmpeg_bin:
        raise PipelineStageError(
            STAGE_BURN, "ffmpeg_unavailable", "FFmpeg no disponible en el sistema"
        )
    if not video_path or not os.path.isfile(video_path):
        raise PipelineStageError(
            STAGE_BURN, "burn_in_error", "vídeo de entrada no encontrado"
        )
    if cancel_event is not None and cancel_event.is_set():
        raise TranscriptionCancelledError("pipeline cancelada")
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    duration_ms = VideoBurnerService.get_video_duration_ms(video_path, ffmpeg_bin)
    duration_sec = duration_ms / 1000.0 if duration_ms else 0.0
    width, height = VideoBurnerService.get_video_dimensions(video_path, ffmpeg_bin)
    temp_dir = tempfile.mkdtemp(prefix="srt4u_burn_")
    try:
        ass_content = VideoBurnerService.generate_ass_script(
            items, BurnInOptions(), video_width=width, video_height=height
        )
        ass_path = os.path.join(temp_dir, "subtitles.ass")
        stderr_log_path = os.path.join(temp_dir, "ffmpeg_stderr.log")
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            os.path.abspath(video_path),
            "-vf",
            "ass=subtitles.ass",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "copy",
            "-progress",
            "pipe:1",
            os.path.abspath(output_path),
        ]
        with open(stderr_log_path, "w", encoding="utf-8") as stderr_file:
            process = subprocess.Popen(
                cmd,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        current_sec = 0.0
        assert process.stdout is not None
        while True:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except OSError:
                    pass
                raise TranscriptionCancelledError("pipeline cancelada")
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    current_sec = int(line.split("=")[1]) / 1000000.0
                except ValueError:
                    pass
            if line.startswith("progress=") and duration_sec > 0:
                if progress_callback is not None:
                    progress_callback(
                        {
                            "ratio": min(1.0, max(0.0, current_sec / duration_sec)),
                            "current_sec": current_sec,
                        }
                    )
        process.wait()
        if process.returncode != 0:
            stderr_tail = ""
            try:
                with open(
                    stderr_log_path, "r", encoding="utf-8", errors="replace"
                ) as ef:
                    stderr_tail = ef.read()[-2000:]
            except OSError:
                pass
            logger.error(
                "FFmpeg falló (código %s): %s", process.returncode, stderr_tail
            )
            raise PipelineStageError(
                STAGE_BURN,
                "burn_in_error",
                f"FFmpeg finalizó con código {process.returncode}",
            )
    finally:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)
    if progress_callback is not None:
        progress_callback({"ratio": 1.0})
    return output_path


def record_pipeline_result(
    result: PipelineResult,
    config: PipelineConfig,
    db_path: Optional[str] = None,
    *,
    file_path: Optional[str] = None,
) -> Optional[int]:
    """One main ``pipeline`` history row with execution aggregates only."""
    from .history_store import record_safely

    metrics = result.translation_metrics
    transcription = result.transcription_result
    qa_after = result.qa_after or {}
    return record_safely(
        "pipeline",
        db_path,
        file_path=file_path or config.input_media,
        file_format=config.output_format,
        source_language=(
            (transcription.language if transcription else None)
            or config.source_language
        ),
        target_language=config.target_language,
        provider=(
            (metrics.provider if metrics is not None else None)
            or (transcription.provider if transcription else None)
            or "pipeline"
        ),
        requested_provider=(
            config.provider if config.translation_enabled else "pipeline"
        ),
        model=(transcription.model if transcription else None),
        number_of_cues=(result.analytics_after or {})
        .get("content", {})
        .get("subtitle_count"),
        media_duration_ms=result.media_duration_ms,
        duration_ms=result.total_duration_ms,
        success=1 if result.success else 0,
        error_type=(
            result.errors[0]["error_type"]
            if result.errors and not result.success
            else None
        ),
        retry_count=(metrics.retry_count if metrics is not None else 0),
        fallback_used=(bool(metrics.fallback_used) if metrics is not None else False),
        qa_errors=qa_after.get("error_count", 0),
        qa_warnings=qa_after.get("warning_count", 0),
        translation_failures=result.translation_failures,
    )
