import re
import os
import time
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Tuple

from ..logging_setup import get_logger
from .translation_service import TranslationService
from .subtitle_analytics import SubtitleAnalytics, SubtitleAnalyticsService
from .subtitle_qa import QAReport, QARules, SubtitleQA
from .translation_models import TranslationMetrics

logger = get_logger("subtitles")


def ms_to_srt_time(ms: int) -> str:
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def ms_to_vtt_time(ms: int) -> str:
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def ms_to_ass_time(ms: int) -> str:
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    centiseconds = (ms % 1000) // 10
    return f"{hours:01d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def parse_timestamp_to_ms(time_str: str) -> int:
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split(".")
        s = int(s_parts[0])
        ms = int(s_parts[1].ljust(3, "0")[:3]) if len(s_parts) > 1 else 0
        return (h * 3600 + m * 60 + s) * 1000 + ms
    elif len(parts) == 2:
        m = int(parts[0])
        s_parts = parts[1].split(".")
        s = int(s_parts[0])
        ms = int(s_parts[1].ljust(3, "0")[:3]) if len(s_parts) > 1 else 0
        return (m * 60 + s) * 1000 + ms
    return 0


@dataclass
class SubtitleItem:
    index: int
    start_ms: int
    end_ms: int
    text: str
    style: str = "Default"
    extra: str = ""

    def get_srt_time(self) -> str:
        return f"{ms_to_srt_time(self.start_ms)} --> {ms_to_srt_time(self.end_ms)}"

    def get_vtt_time(self) -> str:
        return f"{ms_to_vtt_time(self.start_ms)} --> {ms_to_vtt_time(self.end_ms)}"

    def get_ass_start(self) -> str:
        return ms_to_ass_time(self.start_ms)

    def get_ass_end(self) -> str:
        return ms_to_ass_time(self.end_ms)


@dataclass
class ProcessingStats:
    total_lines: int = 0
    deleted_lines: int = 0
    processed_items_count: int = 0
    elapsed_time: float = 0.0
    # Bloques que el motor de traducción no pudo traducir (mantienen el texto original)
    translation_failures: int = 0


@dataclass
class ProcessingResult:
    stats: ProcessingStats
    original_items: List[SubtitleItem] = field(default_factory=list)
    processed_items: List[SubtitleItem] = field(default_factory=list)
    output_content: str = ""
    analytics: Optional[SubtitleAnalytics] = None
    qa_report: Optional[QAReport] = None
    translation_metrics: Optional[TranslationMetrics] = None


class SubtitleService:
    """
    Motor de procesamiento de subtítulos para SRT, VTT, ASS y TXT.
    """

    DEFAULT_SPAM_PATTERNS = [
        r"(?i)subtitled?\s*by\b.*",
        r"(?i)subt[ií]tulos\s*por\b.*",
        r"(?i)traducci[oó]n\s*(?:de|por)\b.*",
        r"(?i)ripped\s*by\b.*",
        r"(?i)sincronizad[oa]\s*por\b.*",
        r"(?i)downloaded\s*from\b.*",
        r"(?i)descargad[oa]\s*de\b.*",
        r"(?i)https?://[^\s]+",
        r"(?i)www\.[a-z0-9\-\.]+\.[a-z]{2,}",
        r"(?i)t\.me/[a-zA-Z0-9_\-]+",
        r"(?i)joinchat/[a-zA-Z0-9_\-]+",
        r"(?i)telegram:?\s*@[a-zA-Z0-9_]+",
        r"[-~]?♪.*?♪[-~]?",
        r"♪+",
        r"♫+",
        r"(?i)we\s*compress\s*knowledge\s*for\s*you!?",
        r"(?i)\b(?:yts|rarbg|yify|opensubtitles|addic7ed|subscene)\b.*",
        r"(?i)<font[^>]*>.*?</font>",
    ]

    def __init__(
        self,
        translation_service: Optional[TranslationService] = None,
        batch_size: int = 50,
        qa_rules: Optional[QARules] = None,
    ):
        self.translation_service = translation_service or TranslationService()
        self.batch_size = batch_size
        self.qa_service = SubtitleQA(qa_rules)
        self.analytics_service = SubtitleAnalyticsService(qa_rules)
        self.last_translation_metrics: Optional[TranslationMetrics] = None
        self._last_translation_started_at: Optional[float] = None
        self.last_translation_failures = 0
        self.spam_patterns = [re.compile(p) for p in self.DEFAULT_SPAM_PATTERNS]
        cpu_threads = os.cpu_count() or 4
        self.max_workers = max(1, round(cpu_threads * 0.8))

    def detect_format(self, content: str, file_path: Optional[str] = None) -> str:
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".srt", ".vtt", ".ass", ".ssa", ".txt"]:
                return "ass" if ext in [".ass", ".ssa"] else ext.lstrip(".")

        stripped = content.strip()
        if stripped.startswith("WEBVTT"):
            return "vtt"
        if "[Script Info]" in content or "[Events]" in content:
            return "ass"
        if "\n00:" in content or "\n1\n00:" in content or " --> " in content:
            return "srt"
        return "txt"

    def parse_subtitles(
        self, content: str, file_format: str = "srt"
    ) -> List[SubtitleItem]:
        format_lower = file_format.lower()
        if format_lower == "vtt":
            return self._parse_vtt(content)
        elif format_lower in ["ass", "ssa"]:
            return self._parse_ass(content)
        elif format_lower == "txt":
            return self._parse_txt(content)
        return self._parse_srt(content)

    def _parse_srt(self, content: str) -> List[SubtitleItem]:
        items: List[SubtitleItem] = []
        raw_blocks = re.split(r"\r?\n\s*\r?\n", content.strip())
        ts_regex = re.compile(
            r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})"
        )

        curr_idx = 1
        for block in raw_blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            time_line_idx = -1
            match = None
            for idx, line in enumerate(lines[:3]):
                match = ts_regex.search(line)
                if match:
                    time_line_idx = idx
                    break

            if match and time_line_idx >= 0:
                start_ms = parse_timestamp_to_ms(match.group(1))
                end_ms = parse_timestamp_to_ms(match.group(2))
                text = "\n".join(lines[time_line_idx + 1 :])
                if text.strip():
                    items.append(
                        SubtitleItem(
                            index=curr_idx, start_ms=start_ms, end_ms=end_ms, text=text
                        )
                    )
                    curr_idx += 1
        return items

    def _parse_vtt(self, content: str) -> List[SubtitleItem]:
        lines = content.splitlines()
        items: List[SubtitleItem] = []
        ts_regex = re.compile(
            r"((?:\d{1,2}:)?\d{2}:\d{2}[\.]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[\.]\d{1,3})"
        )

        curr_idx = 1
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
                i += 1
                continue

            match = ts_regex.search(line)
            extra = ""
            if not match and i + 1 < len(lines):
                match = ts_regex.search(lines[i + 1].strip())
                if match:
                    line = lines[i + 1].strip()
                    i += 1

            if match:
                start_ms = parse_timestamp_to_ms(match.group(1))
                end_ms = parse_timestamp_to_ms(match.group(2))
                time_line_full = line
                after_match = time_line_full[match.end() :].strip()
                if after_match:
                    extra = after_match

                text_lines = []
                i += 1
                while i < len(lines) and lines[i].strip():
                    text_lines.append(lines[i].strip())
                    i += 1

                text = "\n".join(text_lines)
                if text.strip():
                    items.append(
                        SubtitleItem(
                            index=curr_idx,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            text=text,
                            extra=extra,
                        )
                    )
                    curr_idx += 1
            else:
                i += 1
        return items

    def _parse_ass(self, content: str) -> List[SubtitleItem]:
        items: List[SubtitleItem] = []
        dialogue_regex = re.compile(
            r"^Dialogue:\s*[^,]+,([^,]+),([^,]+),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),(.*)$",
            re.IGNORECASE,
        )
        curr_idx = 1
        for line in content.splitlines():
            line_str = line.strip()
            if not line_str.startswith("Dialogue:"):
                continue

            match = dialogue_regex.match(line_str)
            if match:
                start_str, end_str, style = (
                    match.group(1),
                    match.group(2),
                    match.group(3),
                )
                raw_text = match.group(9)
                start_ms = parse_timestamp_to_ms(start_str)
                end_ms = parse_timestamp_to_ms(end_str)
                text = raw_text.replace(r"\N", "\n").replace(r"\n", "\n")
                items.append(
                    SubtitleItem(
                        index=curr_idx,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text,
                        style=style,
                    )
                )
                curr_idx += 1
        return items

    def _parse_txt(self, content: str) -> List[SubtitleItem]:
        items: List[SubtitleItem] = []
        curr_ms = 0
        curr_idx = 1
        for line in content.splitlines():
            text = line.strip()
            if not text:
                continue
            duration = max(2000, len(text) * 60)
            items.append(
                SubtitleItem(
                    index=curr_idx,
                    start_ms=curr_ms,
                    end_ms=curr_ms + duration,
                    text=text,
                )
            )
            curr_ms += duration + 500
            curr_idx += 1
        return items

    def analyze_subtitles(
        self,
        items: List[SubtitleItem],
        *,
        file_format: Optional[str] = None,
        source_content: Optional[str] = None,
        processing_time_seconds: float = 0.0,
        lines_removed: int = 0,
        translation_failures: int = 0,
        reference_items: Optional[List[SubtitleItem]] = None,
    ) -> Tuple[SubtitleAnalytics, QAReport]:
        """Return reusable analytics and deterministic QA for already-parsed cues."""
        report = self.qa_service.validate(
            items, file_format, source_content, reference_items
        )
        analytics = self.analytics_service.analyze(
            items,
            file_format=file_format,
            source_content=source_content,
            processing_time_seconds=processing_time_seconds,
            lines_removed=lines_removed,
            translation_failures=translation_failures,
            qa_report=report,
        )
        return analytics, report

    def qa_subtitles(
        self,
        items: List[SubtitleItem],
        *,
        file_format: Optional[str] = None,
        source_content: Optional[str] = None,
        reference_items: Optional[List[SubtitleItem]] = None,
    ) -> QAReport:
        """Run only QA on parsed cues, independently of analytics and presentation."""
        return self.qa_service.validate(
            items, file_format, source_content, reference_items
        )

    def qa_file(self, file_path: str) -> QAReport:
        """Read and parse one subtitle file, returning its standalone QA report."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as source_file:
            content = source_file.read()
        file_format = self.detect_format(content, file_path)
        items = self.parse_subtitles(content, file_format)
        return self.qa_subtitles(items, file_format=file_format, source_content=content)

    def analyze_file(self, file_path: str) -> Tuple[SubtitleAnalytics, QAReport]:
        """Read, detect, and parse a subtitle file once before returning analytics and QA."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as source_file:
            content = source_file.read()
        file_format = self.detect_format(content, file_path)
        items = self.parse_subtitles(content, file_format)
        return self.analyze_subtitles(
            items, file_format=file_format, source_content=content
        )

    def clean_subtitles(
        self, items: List[SubtitleItem]
    ) -> Tuple[List[SubtitleItem], int, int]:
        cleaned_items: List[SubtitleItem] = []
        total_lines = 0
        deleted_lines = 0

        for item in items:
            lines = item.text.split("\n")
            kept_lines = []
            for line in lines:
                total_lines += 1
                is_spam = False
                for pattern in self.spam_patterns:
                    if pattern.search(line):
                        is_spam = True
                        deleted_lines += 1
                        break
                if not is_spam and line.strip():
                    kept_lines.append(line.strip())

            if kept_lines:
                item_cleaned = SubtitleItem(
                    index=len(cleaned_items) + 1,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    text="\n".join(kept_lines),
                    style=item.style,
                    extra=item.extra,
                )
                cleaned_items.append(item_cleaned)

        return cleaned_items, total_lines, deleted_lines

    def translate_subtitles(
        self,
        items: List[SubtitleItem],
        target_language: str,
        source_language: str = "auto",
        engine: str = "google",
        parallel: bool = True,
        progress_callback: Optional[Callable[[str, object], None]] = None,
    ) -> List[SubtitleItem]:
        total_items = len(items)
        self._last_translation_started_at = time.perf_counter()
        self.last_translation_failures = 0
        self.last_translation_metrics = None
        if total_items == 0:
            self.last_translation_metrics = TranslationMetrics.aggregate(
                [],
                source_language=source_language,
                target_language=target_language,
                number_of_cues=0,
                characters_input=0,
                characters_output=0,
                words_input=0,
                words_output=0,
                duration_ms=0,
                success=True,
                requested_provider=engine,
            )
            return []

        results: List[Optional[SubtitleItem]] = [None] * total_items
        failed_indices: List[int] = []
        translation_metrics: List[TranslationMetrics] = []
        metric_failures: List[str] = []
        translation_errors: List[str] = []

        def translate_single_item(
            idx: int, item: SubtitleItem
        ) -> Tuple[int, SubtitleItem]:
            original_text = item.text.strip()
            if not original_text:
                return idx, item

            try:
                if hasattr(self.translation_service, "clear_last_result"):
                    self.translation_service.clear_last_result()
                translated_text = self.translation_service.translate_text(
                    text=original_text,
                    target_language=target_language,
                    source_language=source_language,
                    engine=engine,
                )
                last_result = getattr(self.translation_service, "last_result", None)
                engine_error = getattr(self.translation_service, "last_error", None)
                if last_result is not None:
                    translation_metrics.append(last_result.metrics)
                else:
                    translation_metrics.append(
                        TranslationMetrics.for_text(
                            provider=engine,
                            model=None,
                            source_language=source_language,
                            target_language=target_language,
                            source_text=original_text,
                            translated_text=translated_text,
                            duration_ms=0,
                            success=engine_error is None,
                            error_type="unknown" if engine_error else None,
                            requested_provider=engine,
                            providers_used=[engine],
                            error_message="unknown" if engine_error else None,
                        )
                    )
                if engine_error:
                    failed_indices.append(item.index)
                    metric_failures.append(engine_error)
                    translation_metrics[-1].success = False
                    if last_result is None:
                        translation_metrics[-1].error_type = "unknown"
                    translation_errors.append(
                        getattr(
                            getattr(last_result, "metrics", None),
                            "error_type",
                            "unknown",
                        )
                    )
                    logger.warning(
                        "El provider '%s' no pudo traducir el cue %s: error_type=%s",
                        engine,
                        item.index,
                        getattr(
                            getattr(last_result, "metrics", None),
                            "error_type",
                            "unknown",
                        ),
                    )
                new_item = SubtitleItem(
                    index=item.index,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    text=translated_text,
                    style=item.style,
                    extra=item.extra,
                )
                return idx, new_item
            except Exception as exc:
                failed_indices.append(item.index)
                metric_failures.append(type(exc).__name__)
                translation_errors.append("unknown")
                translation_metrics.append(
                    TranslationMetrics.for_text(
                        provider=engine,
                        model=None,
                        source_language=source_language,
                        target_language=target_language,
                        source_text=original_text,
                        translated_text=original_text,
                        duration_ms=0,
                        success=False,
                        error_type="unknown",
                        requested_provider=engine,
                        providers_used=[engine],
                        error_message=type(exc).__name__,
                    )
                )
                logger.exception(
                    "Excepción al traducir el bloque %s con el provider '%s'",
                    item.index,
                    engine,
                )
                return idx, item

        completed = 0
        if parallel:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                future_to_idx = {
                    executor.submit(translate_single_item, i, item): i
                    for i, item in enumerate(items)
                }
                for future in concurrent.futures.as_completed(future_to_idx):
                    idx, res_item = future.result()
                    results[idx] = res_item
                    completed += 1
                    if progress_callback:
                        progress_callback("step_translating", (completed, total_items))
        else:
            for i, item in enumerate(items):
                idx, res_item = translate_single_item(i, item)
                results[idx] = res_item
                completed += 1
                if progress_callback:
                    progress_callback("step_translating", (completed, total_items))

        self.last_translation_failures = len(failed_indices)
        if translation_metrics:
            providers_used = list(
                dict.fromkeys(
                    provider
                    for metric in translation_metrics
                    for provider in (metric.providers_used or [metric.provider])
                )
            )
        else:
            providers_used = []
        input_texts = [item.text.strip() for item in items if item.text.strip()]
        output_texts = [
            item.text.strip() for item in results if item and item.text.strip()
        ]
        failed = bool(failed_indices)
        self.last_translation_metrics = TranslationMetrics.aggregate(
            translation_metrics,
            source_language=source_language,
            target_language=target_language,
            number_of_cues=len(input_texts),
            characters_input=sum(len(text) for text in input_texts),
            characters_output=sum(len(text) for text in output_texts),
            words_input=sum(len(text.split()) for text in input_texts),
            words_output=sum(len(text.split()) for text in output_texts),
            duration_ms=(
                int((time.perf_counter() - self._last_translation_started_at) * 1000)
                if self._last_translation_started_at is not None
                else None
            ),
            success=not failed,
            requested_provider=engine,
            providers_used=providers_used,
            error_type=translation_errors[0] if translation_errors else None,
            error_message=None,
            fallback_error_type=next(
                (
                    metric.fallback_error_type
                    for metric in translation_metrics
                    if metric.fallback_error_type
                ),
                None,
            ),
        )
        if metric_failures and self.last_translation_metrics.success is False:
            # Do not retain raw exception messages that could contain sensitive data.
            self.last_translation_metrics.error_message = translation_errors[0]
        if failed_indices:
            logger.warning(
                "Traducción incompleta: %s de %s cues mantienen el texto original (error_type=%s)",
                self.last_translation_failures,
                total_items,
                translation_errors[0] if translation_errors else "unknown",
            )

        return [it for it in results if it is not None]

    def format_output(
        self, items: List[SubtitleItem], target_format: str = "srt"
    ) -> str:
        fmt = target_format.lower().lstrip(".")
        if fmt == "vtt":
            return self._format_vtt(items)
        elif fmt in ["ass", "ssa"]:
            return self._format_ass(items)
        elif fmt == "txt":
            return self._format_txt(items)
        return self._format_srt(items)

    def _format_srt(self, items: List[SubtitleItem]) -> str:
        blocks = []
        for idx, item in enumerate(items, 1):
            blocks.append(f"{idx}\n{item.get_srt_time()}\n{item.text}\n")
        return "\n".join(blocks).strip() + "\n"

    def _format_vtt(self, items: List[SubtitleItem]) -> str:
        lines = ["WEBVTT\n"]
        for idx, item in enumerate(items, 1):
            cue_line = item.get_vtt_time()
            if item.extra:
                cue_line += f" {item.extra}"
            lines.append(f"{idx}\n{cue_line}\n{item.text}\n")
        return "\n".join(lines).strip() + "\n"

    def _format_ass(self, items: List[SubtitleItem]) -> str:
        header = """[Script Info]
Title: SRT4U Exported Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for item in items:
            ass_text = item.text.replace("\n", r"\N")
            start = item.get_ass_start()
            end = item.get_ass_end()
            style = item.style or "Default"
            events.append(f"Dialogue: 0,{start},{end},{style},,0,0,0,,{ass_text}")
        return header + "\n".join(events) + "\n"

    def _format_txt(self, items: List[SubtitleItem]) -> str:
        return "\n".join(item.text for item in items).strip() + "\n"

    def process_subtitles(
        self,
        file_path: str,
        do_clean: bool = True,
        do_translate: bool = False,
        target_language: Optional[str] = None,
        source_language: str = "auto",
        engine: str = "google",
        target_format: Optional[str] = None,
        parallel: bool = True,
        progress_callback: Optional[Callable[[str, object], None]] = None,
    ) -> ProcessingResult:
        start_time = time.time()

        # Paso 1: Lectura
        if progress_callback:
            progress_callback("step_reading", True)

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        source_format = self.detect_format(content, file_path)
        out_format = target_format or source_format

        # Paso 2: Análisis
        if progress_callback:
            progress_callback("step_analyzing", True)

        original_items = self.parse_subtitles(content, source_format)
        current_items = list(original_items)
        total_original_lines = sum(len(it.text.split("\n")) for it in original_items)
        deleted_lines_count = 0

        # Paso 3: Limpieza
        if do_clean:
            if progress_callback:
                progress_callback("step_cleaning", True)
            current_items, total_original_lines, deleted_lines_count = (
                self.clean_subtitles(current_items)
            )

        # Paso 4: Traducción
        translation_failures = 0
        if do_translate and target_language:
            if progress_callback:
                progress_callback("step_translating", (0, len(current_items)))
            current_items = self.translate_subtitles(
                items=current_items,
                target_language=target_language,
                source_language=source_language,
                engine=engine,
                parallel=parallel,
                progress_callback=progress_callback,
            )
            translation_failures = self.last_translation_failures

        # Paso 5: Aplicar formato original
        if progress_callback:
            progress_callback("step_formatting", True)

        output_content = self.format_output(current_items, out_format)

        # Paso 6: Guardado
        if progress_callback:
            progress_callback("step_saving", True)

        analytics, qa_report = self.analyze_subtitles(
            current_items,
            file_format=out_format,
            source_content=output_content,
            lines_removed=deleted_lines_count,
            translation_failures=translation_failures,
            reference_items=original_items if do_translate else None,
        )
        elapsed = time.time() - start_time
        stats = ProcessingStats(
            total_lines=total_original_lines,
            deleted_lines=deleted_lines_count,
            processed_items_count=len(current_items),
            elapsed_time=round(elapsed, 2),
            translation_failures=translation_failures,
        )
        analytics.processing.processing_time_seconds = round(elapsed, 3)

        return ProcessingResult(
            stats=stats,
            original_items=original_items,
            processed_items=current_items,
            output_content=output_content,
            analytics=analytics,
            qa_report=qa_report,
            translation_metrics=self.last_translation_metrics if do_translate else None,
        )
