"""Structured subtitle content, timing, quality, and processing analytics."""

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Dict, Optional

from .subtitle_qa import QARules, QAReport, SubtitleQA

if TYPE_CHECKING:
    from .subtitle_service import SubtitleItem


@dataclass
class ContentMetrics:
    subtitle_count: int = 0
    total_words: int = 0
    total_characters: int = 0
    average_characters_per_subtitle: float = 0.0
    max_characters_per_subtitle: int = 0
    average_words_per_subtitle: float = 0.0
    line_count: int = 0
    average_lines_per_subtitle: float = 0.0
    empty_subtitles: int = 0
    duplicate_subtitles: int = 0


@dataclass
class TimingMetrics:
    total_duration_ms: int = 0
    average_cps: float = 0.0
    max_cps: float = 0.0
    min_cps: float = 0.0
    overlapping_subtitles: int = 0
    too_short_subtitles: int = 0
    too_long_subtitles: int = 0
    cps_violations: int = 0


@dataclass
class QualityMetrics:
    line_length_violations: int = 0
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    rule_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class ProcessingMetrics:
    processing_time_seconds: float = 0.0
    lines_removed: int = 0
    translation_failures: int = 0


@dataclass
class SubtitleAnalytics:
    content: ContentMetrics = field(default_factory=ContentMetrics)
    timing: TimingMetrics = field(default_factory=TimingMetrics)
    quality: QualityMetrics = field(default_factory=QualityMetrics)
    processing: ProcessingMetrics = field(default_factory=ProcessingMetrics)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class SubtitleAnalyticsService:
    """Computes deterministic metrics over the domain cue model."""

    def __init__(self, rules: Optional[QARules] = None):
        self.qa = SubtitleQA(rules)

    def analyze(
        self,
        items: list["SubtitleItem"],
        *,
        file_format: Optional[str] = None,
        source_content: Optional[str] = None,
        processing_time_seconds: float = 0.0,
        lines_removed: int = 0,
        translation_failures: int = 0,
        qa_report: Optional[QAReport] = None,
    ) -> SubtitleAnalytics:
        report = qa_report or self.qa.validate(items, file_format, source_content)
        cue_count = len(items)

        character_counts: list[int] = []
        word_counts: list[int] = []
        line_counts: list[int] = []
        normalized_texts: list[str] = []
        empty_subtitles = 0
        min_start: Optional[int] = None
        max_end: Optional[int] = None
        cps_values: list[float] = []

        for item in items:
            raw_text = item.text or ""
            if not raw_text.strip():
                empty_subtitles += 1
            line_counts.append(len(raw_text.splitlines()) if raw_text else 0)

            visible = self.qa.visible_text(raw_text)
            chars = sum(len(line) for line in visible.splitlines())
            character_counts.append(chars)

            words = visible.split()
            word_counts.append(len(words))
            normalized_texts.append(" ".join(words).casefold())

            if item.start_ms >= 0 and item.end_ms > item.start_ms:
                if min_start is None or item.start_ms < min_start:
                    min_start = item.start_ms
                if max_end is None or item.end_ms > max_end:
                    max_end = item.end_ms
                duration = item.end_ms - item.start_ms
                if chars > 0:
                    cps_values.append(chars / (duration / 1000.0))

        content = ContentMetrics(
            subtitle_count=cue_count,
            total_words=sum(word_counts),
            total_characters=sum(character_counts),
            average_characters_per_subtitle=(
                round(sum(character_counts) / cue_count, 3) if cue_count else 0.0
            ),
            max_characters_per_subtitle=max(character_counts, default=0),
            average_words_per_subtitle=(
                round(sum(word_counts) / cue_count, 3) if cue_count else 0.0
            ),
            line_count=sum(line_counts),
            average_lines_per_subtitle=(
                round(sum(line_counts) / cue_count, 3) if cue_count else 0.0
            ),
            empty_subtitles=empty_subtitles,
            duplicate_subtitles=self._duplicate_count(normalized_texts),
        )

        duration_span = (
            (max_end - min_start)
            if min_start is not None and max_end is not None
            else 0
        )

        rule_counts: Dict[str, int] = {}
        rule_indices: Dict[str, set] = {
            "overlap": set(),
            "duration_too_short": set(),
            "duration_too_long": set(),
            "cps_exceeded": set(),
            "line_too_long": set(),
        }
        for finding in report.findings:
            rule = finding.rule
            rule_counts[rule] = rule_counts.get(rule, 0) + 1
            if rule in rule_indices and finding.subtitle_index is not None:
                rule_indices[rule].add(finding.subtitle_index)

        timing = TimingMetrics(
            total_duration_ms=max(0, duration_span),
            average_cps=round(sum(cps_values) / len(cps_values), 3)
            if cps_values
            else 0.0,
            max_cps=round(max(cps_values), 3) if cps_values else 0.0,
            min_cps=round(min(cps_values), 3) if cps_values else 0.0,
            overlapping_subtitles=len(rule_indices["overlap"]),
            too_short_subtitles=len(rule_indices["duration_too_short"]),
            too_long_subtitles=len(rule_indices["duration_too_long"]),
            cps_violations=len(rule_indices["cps_exceeded"]),
        )
        quality = QualityMetrics(
            line_length_violations=len(rule_indices["line_too_long"]),
            errors=report.error_count,
            warnings=report.warning_count,
            infos=report.info_count,
            rule_counts=rule_counts,
        )
        processing = ProcessingMetrics(
            processing_time_seconds=round(max(0.0, processing_time_seconds), 3),
            lines_removed=max(0, lines_removed),
            translation_failures=max(0, translation_failures),
        )
        return SubtitleAnalytics(content, timing, quality, processing)

    @staticmethod
    def _duplicate_count(normalized_texts: list[str]) -> int:
        seen = set()
        duplicate_count = 0
        for text in normalized_texts:
            if text and text in seen:
                duplicate_count += 1
            elif text:
                seen.add(text)
        return duplicate_count
