"""Reproducible translation provider benchmarking without PyQt6 or network.

The benchmark reuses :class:`TranslationService` and
:class:`TranslationMetrics` aggregation; it only orchestrates repeated,
per-provider executions over a fixed cue dataset and records one structured
row per (provider, run) pair for later offline analysis (Python/Pandas/Jupyter).
"""

import csv
import io
import json
import platform
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..logging_setup import get_logger
from .translation_models import TranslationMetrics
from .translation_service import TranslationService

logger = get_logger("benchmark")

#: Version of the built-in cue dataset. Bump when cue texts change so that
#: results from different dataset revisions are never silently mixed.
BENCHMARK_DATASET_VERSION = "1"

#: Small, original (copyright-free) English cues covering short, medium, long,
#: dialogue, multiline, tagged, punctuated, and proper-noun content.
DEFAULT_BENCHMARK_CUES: List[str] = [
    "Hello.",
    "Good morning, how are you today?",
    "The train leaves platform nine at half past seven in the morning.",
    "Wait for me!\nI will be right back.",
    "<i>Be careful,</i> the floor is wet.",
    "Really? You did that... yesterday?",
    "Ms. Alvarez and Dr. Chen met in Lisbon last spring.",
    "Please turn off the lights, close the door, and lock it behind you.",
    "The old lighthouse stood on the cliff for over a hundred years.",
    "Yes, no, maybe.\nAsk Ana,\nshe knows.",
]

#: Stable CSV column order: one row per (provider, run) execution.
BENCHMARK_CSV_COLUMNS: List[str] = [
    "benchmark_id",
    "timestamp",
    "run_index",
    "dataset_version",
    "dataset_size",
    "provider",
    "requested_provider",
    "model",
    "source_language",
    "target_language",
    "number_of_cues",
    "characters_input",
    "characters_output",
    "words_input",
    "words_output",
    "duration_ms",
    "success",
    "error_type",
    "retry_count",
    "fallback_used",
    "providers_used",
    "fallback_error_type",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost",
    "cues_per_second",
    "characters_per_second",
    "words_per_second",
    "latency_per_cue_ms",
    "latency_per_1k_chars_ms",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _environment() -> Dict[str, Any]:
    """Best-effort runtime description; never raises."""
    try:
        return {
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
    except Exception:
        return {"python": None, "platform": None}


def _derived_metrics(
    *,
    number_of_cues: int,
    characters_input: int,
    words_input: int,
    duration_ms: Optional[int],
) -> Dict[str, Optional[float]]:
    """Throughput metrics. ``None`` when duration is unknown or zero.

    Names intentionally avoid ``cps``: subtitle CPS (characters per second of
    display time) is a different metric owned by analytics.
    """
    if not duration_ms or duration_ms <= 0:
        return {
            "cues_per_second": None,
            "characters_per_second": None,
            "words_per_second": None,
            "latency_per_cue_ms": None,
            "latency_per_1k_chars_ms": None,
        }
    seconds = duration_ms / 1000.0
    return {
        "cues_per_second": number_of_cues / seconds,
        "characters_per_second": characters_input / seconds,
        "words_per_second": words_input / seconds,
        "latency_per_cue_ms": duration_ms / number_of_cues if number_of_cues else None,
        "latency_per_1k_chars_ms": (duration_ms / characters_input * 1000.0)
        if characters_input
        else None,
    }


@dataclass
class BenchmarkConfig:
    """Validated benchmark plan; individual runs are never auto-merged."""

    providers: List[str]
    source_language: str = "en"
    target_language: str = "es"
    runs: int = 1
    include_texts: bool = False

    def __post_init__(self) -> None:
        providers = [str(name).strip() for name in self.providers or []]
        providers = [name for name in providers if name]
        if not providers:
            raise ValueError("benchmark requires at least one provider")
        if (
            not isinstance(self.runs, int)
            or isinstance(self.runs, bool)
            or self.runs < 1
        ):
            raise ValueError("runs must be a positive integer")
        if not self.source_language or not self.target_language:
            raise ValueError("source and target languages are required")
        self.providers = providers


@dataclass
class BenchmarkRun:
    """One (provider, run_index) execution over the full dataset."""

    benchmark_id: str
    timestamp: str
    run_index: int
    dataset_version: str
    dataset_size: int
    provider: str
    requested_provider: str
    model: Optional[str]
    source_language: str
    target_language: str
    number_of_cues: int
    characters_input: int
    characters_output: int
    words_input: int
    words_output: int
    duration_ms: Optional[int]
    success: bool
    error_type: Optional[str] = None
    retry_count: int = 0
    fallback_used: bool = False
    providers_used: List[str] = field(default_factory=list)
    fallback_error_type: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    cues_per_second: Optional[float] = None
    characters_per_second: Optional[float] = None
    words_per_second: Optional[float] = None
    latency_per_cue_ms: Optional[float] = None
    latency_per_1k_chars_ms: Optional[float] = None
    error_message: Optional[str] = None
    input_texts: Optional[List[str]] = None
    output_texts: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Header plus one row per execution; JSON- and CSV-serializable."""

    benchmark_id: str
    timestamp: str
    dataset_version: str
    dataset_size: int
    config: Dict[str, Any]
    environment: Dict[str, Any]
    runs: List[BenchmarkRun] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "timestamp": self.timestamp,
            "dataset_version": self.dataset_version,
            "dataset_size": self.dataset_size,
            "config": self.config,
            "environment": self.environment,
            "runs": [run.to_dict() for run in self.runs],
        }

    def to_json(self) -> str:
        return (
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )

    def to_csv(self) -> str:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=BENCHMARK_CSV_COLUMNS)
        writer.writeheader()
        for run in self.runs:
            payload = run.to_dict()
            row: Dict[str, Any] = {}
            for column in BENCHMARK_CSV_COLUMNS:
                value = payload.get(column)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                row[column] = value
            writer.writerow(row)
        return output.getvalue()


def load_benchmark_dataset(path: Optional[str] = None) -> Dict[str, Any]:
    """Return ``{"version": ..., "source": ..., "cues": [...]}``.

    ``path`` may be a subtitle file, a directory of subtitle files, or
    ``None`` for the built-in versioned cue list. Cue order is stable
    (sorted paths, file order otherwise).
    """
    if path is None:
        return {
            "version": BENCHMARK_DATASET_VERSION,
            "source": "builtin",
            "cues": list(DEFAULT_BENCHMARK_CUES),
        }
    from .subtitle_service import SubtitleService

    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise ValueError(f"dataset not found: {path}")
    service = SubtitleService()
    cues: List[str] = []
    if candidate.is_file():
        files = [candidate]
    else:
        files = sorted(
            item
            for item in candidate.rglob("*")
            if item.is_file()
            and item.suffix.lower() in {".srt", ".vtt", ".ass", ".ssa", ".txt"}
        )
    if not files:
        raise ValueError(f"no subtitle files found in dataset: {path}")
    for item in files:
        content = item.read_text(encoding="utf-8", errors="replace")
        file_format = service.detect_format(content, str(item))
        for cue in service.parse_subtitles(content, file_format):
            text = cue.text.strip()
            if text:
                cues.append(text)
    if not cues:
        raise ValueError(f"dataset contains no cues: {path}")
    return {
        "version": BENCHMARK_DATASET_VERSION,
        "source": str(candidate),
        "cues": cues,
    }


class TranslationBenchmark:
    """Execute a fixed cue set against providers and record per-run metrics.

    Uses sequential per-cue translation through the shared
    :class:`TranslationService` so results are deterministic in structure;
    wall-time of each provider pass is measured for throughput metrics.
    """

    def __init__(
        self,
        config: BenchmarkConfig,
        translation_service: Optional[TranslationService] = None,
        service_factory: Optional[Callable[[str], TranslationService]] = None,
    ):
        self.config = config
        self.translation_service = translation_service
        self.service_factory = service_factory

    def _service_for(self, provider: str) -> TranslationService:
        if self.service_factory is not None:
            service = self.service_factory(provider)
            if not isinstance(service, TranslationService):
                raise ValueError("service_factory must return a TranslationService")
            return service
        if self.translation_service is not None:
            return self.translation_service
        return TranslationService()

    def run(self, cues: Sequence[str]) -> BenchmarkReport:
        cue_list = [text for text in (str(text) for text in cues) if text.strip()]
        if not cue_list:
            raise ValueError("benchmark dataset is empty")
        benchmark_id = uuid.uuid4().hex
        report = BenchmarkReport(
            benchmark_id=benchmark_id,
            timestamp=_utc_now_iso(),
            dataset_version=BENCHMARK_DATASET_VERSION,
            dataset_size=len(cue_list),
            config={
                "providers": list(self.config.providers),
                "source_language": self.config.source_language,
                "target_language": self.config.target_language,
                "runs": self.config.runs,
                "include_texts": self.config.include_texts,
            },
            environment=_environment(),
        )
        for run_index in range(self.config.runs):
            for provider in self.config.providers:
                report.runs.append(
                    self._run_once(
                        benchmark_id=benchmark_id,
                        run_index=run_index,
                        provider=provider,
                        cues=cue_list,
                    )
                )
        return report

    def _run_once(
        self, *, benchmark_id: str, run_index: int, provider: str, cues: List[str]
    ) -> BenchmarkRun:
        service = self._service_for(provider)
        started = time.perf_counter()
        per_cue: List[TranslationMetrics] = []
        outputs: List[str] = []
        for text in cues:
            try:
                result = service.translate_with_metrics(
                    text,
                    self.config.target_language,
                    self.config.source_language,
                    provider=provider,
                )
                per_cue.append(result.metrics)
                outputs.append(result.text)
            except Exception as exc:  # pragma: no cover - service rarely raises
                logger.exception("Benchmark cue failed for provider %s", provider)
                per_cue.append(
                    TranslationMetrics.for_text(
                        provider=provider,
                        model=None,
                        source_language=self.config.source_language,
                        target_language=self.config.target_language,
                        source_text=text,
                        translated_text=text,
                        duration_ms=0,
                        success=False,
                        error_type="unknown",
                        requested_provider=provider,
                        providers_used=[provider],
                        error_message=type(exc).__name__,
                    )
                )
                outputs.append(text)
        duration_ms = int((time.perf_counter() - started) * 1000)
        failed = [metric for metric in per_cue if not metric.success]
        used = list(
            dict.fromkeys(
                name
                for metric in per_cue
                for name in (metric.providers_used or [metric.provider])
            )
        )
        aggregate = TranslationMetrics.aggregate(
            per_cue,
            source_language=self.config.source_language,
            target_language=self.config.target_language,
            number_of_cues=len(cues),
            characters_input=sum(len(text) for text in cues),
            characters_output=sum(len(text) for text in outputs),
            words_input=sum(len(text.split()) for text in cues),
            words_output=sum(len(text.split()) for text in outputs),
            duration_ms=duration_ms,
            success=not failed,
            requested_provider=provider,
            providers_used=used,
            error_type=failed[0].error_type if failed else None,
            error_message=None,
            fallback_error_type=next(
                (
                    metric.fallback_error_type
                    for metric in per_cue
                    if metric.fallback_error_type
                ),
                None,
            ),
        )
        derived = _derived_metrics(
            number_of_cues=len(cues),
            characters_input=aggregate.characters_input,
            words_input=aggregate.words_input,
            duration_ms=aggregate.duration_ms,
        )
        return BenchmarkRun(
            benchmark_id=benchmark_id,
            timestamp=_utc_now_iso(),
            run_index=run_index,
            dataset_version=BENCHMARK_DATASET_VERSION,
            dataset_size=len(cues),
            provider=aggregate.provider,
            requested_provider=provider,
            model=aggregate.model,
            source_language=self.config.source_language,
            target_language=self.config.target_language,
            number_of_cues=len(cues),
            characters_input=aggregate.characters_input,
            characters_output=aggregate.characters_output,
            words_input=aggregate.words_input,
            words_output=aggregate.words_output,
            duration_ms=aggregate.duration_ms,
            success=aggregate.success,
            error_type=aggregate.error_type,
            retry_count=aggregate.retry_count,
            fallback_used=aggregate.fallback_used,
            providers_used=aggregate.providers_used or [],
            fallback_error_type=aggregate.fallback_error_type,
            input_tokens=aggregate.input_tokens,
            output_tokens=aggregate.output_tokens,
            total_tokens=aggregate.total_tokens,
            estimated_cost=aggregate.estimated_cost,
            error_message=None,
            input_texts=list(cues) if self.config.include_texts else None,
            output_texts=list(outputs) if self.config.include_texts else None,
            **derived,
        )
