import pytest

from application.services.subtitle_analytics import SubtitleAnalyticsService
from application.services.subtitle_qa import QARules
from application.services.subtitle_service import SubtitleItem, SubtitleService


def cue(index, start, end, text):
    return SubtitleItem(index=index, start_ms=start, end_ms=end, text=text)


def test_empty_analytics_is_zeroed():
    analytics = SubtitleAnalyticsService().analyze([])

    assert analytics.content.subtitle_count == 0
    assert analytics.content.total_words == 0
    assert analytics.content.total_characters == 0
    assert analytics.timing.total_duration_ms == 0
    assert analytics.timing.average_cps == 0
    assert analytics.quality.errors == 0


def test_single_cue_content_and_timing_metrics():
    analytics = SubtitleAnalyticsService().analyze(
        [cue(1, 1000, 3000, "Hello world\nAgain")]
    )

    assert analytics.content.subtitle_count == 1
    assert analytics.content.total_words == 3
    assert analytics.content.total_characters == 16
    assert analytics.content.average_characters_per_subtitle == 16
    assert analytics.content.max_characters_per_subtitle == 16
    assert analytics.content.average_words_per_subtitle == 3
    assert analytics.content.line_count == 2
    assert analytics.content.average_lines_per_subtitle == 2
    assert analytics.timing.total_duration_ms == 2000
    assert analytics.timing.average_cps == 8
    assert analytics.timing.max_cps == 8
    assert analytics.timing.min_cps == 8


def test_multiple_cues_metrics_duplicate_empty_and_processing():
    analytics = SubtitleAnalyticsService().analyze(
        [
            cue(1, 0, 2000, "same text"),
            cue(2, 2500, 5500, "same   text"),
            cue(3, 6000, 8000, ""),
        ],
        processing_time_seconds=1.23456,
        lines_removed=4,
        translation_failures=2,
    )

    assert analytics.content.subtitle_count == 3
    assert analytics.content.total_words == 4
    assert analytics.content.total_characters == 20
    assert analytics.content.duplicate_subtitles == 1
    assert analytics.content.empty_subtitles == 1
    assert analytics.timing.total_duration_ms == 8000
    assert analytics.timing.average_cps == pytest.approx(4.083, abs=0.001)
    assert analytics.timing.max_cps == 4.5
    assert analytics.timing.min_cps == pytest.approx(3.667, abs=0.001)
    assert analytics.processing.processing_time_seconds == 1.235
    assert analytics.processing.lines_removed == 4
    assert analytics.processing.translation_failures == 2


def test_analytics_excludes_markup_from_readability_counts():
    analytics = SubtitleAnalyticsService().analyze(
        [cue(1, 0, 3000, r"<i>Hello</i> {\an8}world")]
    )

    assert analytics.content.total_words == 2
    assert analytics.content.total_characters == len("Hello world")
    assert analytics.timing.average_cps == pytest.approx(11 / 3, abs=0.001)


def test_analytics_counts_only_cues_with_positive_duration_for_cps():
    analytics = SubtitleAnalyticsService().analyze(
        [cue(1, 0, 0, "bad interval"), cue(2, 1000, 2000, "valid")]
    )

    assert analytics.timing.average_cps == 5
    assert analytics.timing.min_cps == 5
    assert analytics.timing.max_cps == 5
    assert analytics.quality.errors == 1


def test_analytics_duration_is_span_and_qa_counts_unique_cues():
    service = SubtitleService(qa_rules=QARules(max_cps=2, min_duration_ms=1500))
    items = [
        cue(1, 0, 2000, "long enough to exceed cps"),
        cue(2, 1000, 3000, "also too fast"),
    ]
    analytics, report = service.analyze_subtitles(items)

    assert analytics.timing.total_duration_ms == 3000
    assert analytics.timing.overlapping_subtitles == 2
    assert analytics.timing.cps_violations == 2
    assert report.warning_count >= 4
    serialized = analytics.to_dict()
    assert set(serialized) == {"content", "timing", "quality", "processing"}
    assert serialized["content"]["subtitle_count"] == 2


def test_service_analyze_file_uses_existing_parser_and_preserves_format():
    service = SubtitleService()
    analytics, report = service.analyze_file("tests/fixtures/sample.srt")

    assert analytics.content.subtitle_count == 5
    assert isinstance(report.findings, list)
    assert analytics.quality.rule_counts == {
        finding.rule: sum(item.rule == finding.rule for item in report.findings)
        for finding in report.findings
    }
