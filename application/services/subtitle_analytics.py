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
        texts = [item.text for item in items]
        visible_texts = [self.qa.visible_text(text) for text in texts]
        character_counts = [
            sum(len(line) for line in text.splitlines()) for text in visible_texts
        ]
        word_counts = [len(text.split()) for text in visible_texts]
        line_counts = [len(text.splitlines()) if text else 0 for text in texts]
        normalized_texts = [" ".join(text.split()).casefold() for text in visible_texts]

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
            empty_subtitles=sum(not text.strip() for text in texts),
            duplicate_subtitles=self._duplicate_count(normalized_texts),
        )

        valid_intervals = [
            item for item in items if item.start_ms >= 0 and item.end_ms > item.start_ms
        ]
        duration_span = (
            max(item.end_ms for item in valid_intervals)
            - min(item.start_ms for item in valid_intervals)
            if valid_intervals
            else 0
        )
        durations = [item.end_ms - item.start_ms for item in items]
        cps_values = [
            characters / (duration / 1000)
            for item, characters, duration in zip(
                items, character_counts, durations, strict=True
            )
            if duration > 0 and item.start_ms >= 0 and characters > 0
        ]
        rule_counts: Dict[str, int] = {}
        for finding in report.findings:
            rule_counts[finding.rule] = rule_counts.get(finding.rule, 0) + 1

        timing = TimingMetrics(
            total_duration_ms=max(0, duration_span),
            average_cps=round(sum(cps_values) / len(cps_values), 3)
            if cps_values
            else 0.0,
            max_cps=round(max(cps_values), 3) if cps_values else 0.0,
            min_cps=round(min(cps_values), 3) if cps_values else 0.0,
            overlapping_subtitles=self._count_unique_indices(report, "overlap"),
            too_short_subtitles=self._count_unique_indices(
                report, "duration_too_short"
            ),
            too_long_subtitles=self._count_unique_indices(report, "duration_too_long"),
            cps_violations=self._count_unique_indices(report, "cps_exceeded"),
        )
        quality = QualityMetrics(
            line_length_violations=self._count_unique_indices(report, "line_too_long"),
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
    def _count_unique_indices(report: QAReport, rule: str) -> int:
        return len(
            {
                finding.subtitle_index
                for finding in report.findings
                if finding.rule == rule
            }
        )

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
