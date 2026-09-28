import pytest

from application.services.subtitle_qa import (
    QAFinding,
    QARules,
    SubtitleQA,
    SubtitleQARule,
)
from application.services.subtitle_service import SubtitleItem, SubtitleService


def cue(index, start, end, text):
    return SubtitleItem(index=index, start_ms=start, end_ms=end, text=text)


def rules(**overrides):
    values = {
        "max_cps": 15,
        "max_characters_per_line": 42,
        "max_lines": 2,
        "min_duration_ms": 1000,
        "max_duration_ms": 7000,
    }
    values.update(overrides)
    return QARules(**values)


def test_empty_file_is_reported_without_crashing():
    analytics, report = SubtitleService().analyze_subtitles(
        [], file_format="srt", source_content=""
    )

    assert analytics.content.subtitle_count == 0
    assert any(finding.rule == "empty_file" for finding in report.findings)
    assert report.warning_count == 1


def test_detects_invalid_interval_empty_cue_and_severity():
    report = SubtitleQA().validate([cue(1, 1000, 1000, ""), cue(2, 0, 500, "short")])

    assert {finding.rule for finding in report.findings} >= {
        "invalid_timecode",
        "empty_subtitle",
        "duration_too_short",
    }
    assert report.error_count == 1
    assert report.warning_count >= 2
    assert not report.passed
    finding = next(item for item in report.findings if item.rule == "invalid_timecode")
    assert finding.subtitle_index == 1
    assert finding.metadata == {"start_ms": 1000, "end_ms": 1000}


def test_detects_overlap_without_treating_touching_edges_as_overlap():
    report = SubtitleQA().validate(
        [
            cue(1, 0, 2000, "first"),
            cue(2, 1500, 3000, "second"),
            cue(3, 3000, 4000, "third"),
        ]
    )
    overlaps = [finding for finding in report.findings if finding.rule == "overlap"]

    assert len(overlaps) == 2
    assert overlaps[0].metadata["overlaps_with"] == [2]
    assert overlaps[1].metadata["overlaps_with"] == [1]


def test_detects_one_millisecond_overlap_but_not_consecutive_cues():
    report = SubtitleQA().validate(
        [
            cue(1, 0, 1001, "first"),
            cue(2, 1000, 2000, "overlap"),
            cue(3, 2000, 3000, "touching"),
        ]
    )
    overlaps = [finding for finding in report.findings if finding.rule == "overlap"]

    assert [finding.subtitle_index for finding in overlaps] == [1, 2]
    assert overlaps[0].metadata["overlaps_with"] == [2]
    assert overlaps[1].metadata["overlaps_with"] == [1]


def test_detects_long_duration_high_cps_and_long_lines():
    report = SubtitleQA(
        rules(max_cps=5, max_characters_per_line=10, max_duration_ms=3000)
    ).validate([cue(4, 0, 4000, "this line is much too long")])

    assert {finding.rule for finding in report.findings} >= {
        "duration_too_long",
        "cps_exceeded",
        "line_too_long",
    }


def test_threshold_boundaries_are_accepted():
    report = SubtitleQA(
        rules(
            max_cps=5,
            max_characters_per_line=5,
            min_duration_ms=1000,
            max_duration_ms=2000,
        )
    ).validate([cue(1, 0, 1000, "12345"), cue(2, 2000, 4000, "12345")])

    assert not any(
        finding.rule
        in {"duration_too_short", "duration_too_long", "cps_exceeded", "line_too_long"}
        for finding in report.findings
    )


def test_line_and_line_count_boundaries_and_violations():
    qa = SubtitleQA(rules(max_characters_per_line=5, max_lines=2, max_cps=100))
    exact = qa.validate([cue(1, 0, 5000, "12345\n67890")])
    assert not any(
        finding.rule in {"line_too_long", "too_many_lines"}
        for finding in exact.findings
    )

    over = qa.validate([cue(1, 0, 5000, "123456\nline\nthird")])
    assert {finding.rule for finding in over.findings} >= {
        "line_too_long",
        "too_many_lines",
    }


def test_detects_duplicate_text_case_and_whitespace_insensitive():
    report = SubtitleQA().validate(
        [cue(1, 0, 2000, "Hello world"), cue(2, 3000, 5000, " hello   WORLD ")]
    )
    finding = next(
        item for item in report.findings if item.rule == "duplicate_subtitle"
    )

    assert finding.subtitle_index == 2
    assert finding.metadata["first_subtitle_index"] == 1


def test_subtitle_service_exposes_independent_qa_api():
    service = SubtitleService()
    report = service.qa_subtitles(
        [cue(1, 0, 500, "Short")],
        file_format="srt",
        source_content="1\n00:00:00,000 --> 00:00:00,500\nShort\n",
    )
    assert any(finding.rule == "duration_too_short" for finding in report.findings)


def test_raw_srt_timecode_errors_are_found_even_when_parser_omits_cue():
    source = "1\n00:00:02,000 --> 00:00:01,000\nBad time\n\n2\nmalformed\ntext\n"
    service = SubtitleService()
    items = service.parse_subtitles(source, "srt")
    report = service.qa_service.validate(items, "srt", source)
    invalids = [
        finding for finding in report.findings if finding.rule == "invalid_timecode"
    ]

    assert len(invalids) == 2
    assert all(finding.severity == "error" for finding in invalids)


def test_format_checks_vtt_header_and_srt_sequence():
    report = SubtitleQA().validate(
        [],
        file_format="vtt",
        source_content="00:00.000 --> 00:01.000\nMissing header\n",
    )
    assert any(finding.rule == "invalid_format" for finding in report.findings)

    srt_report = SubtitleQA().validate(
        [],
        file_format="srt",
        source_content="3\n00:00:01,000 --> 00:00:02,000\nHello\n",
    )
    assert any(
        finding.rule == "invalid_format" and finding.metadata["declared_index"] == 3
        for finding in srt_report.findings
    )


def test_srt_raw_structure_detects_duplicate_declared_index():
    source = (
        "1\n00:00:00,000 --> 00:00:02,000\nfirst\n\n"
        "1\n00:00:02,000 --> 00:00:04,000\nsecond\n"
    )
    report = SubtitleQA().validate([], "srt", source)
    assert any(finding.rule == "duplicate_index" for finding in report.findings)


def test_detects_formatting_tag_loss_against_reference():
    report = SubtitleQA().validate(
        [cue(1, 0, 2000, "Hola")],
        reference_items=[cue(1, 0, 2000, "<i>Hello</i>")],
    )
    finding = next(
        item for item in report.findings if item.rule == "formatting_tag_mismatch"
    )

    assert finding.severity == "warning"
    assert finding.metadata["expected_tags"] == ["<i>", "</i>"]
    assert finding.metadata["actual_tags"] == []


def test_inline_html_is_not_reported_as_malformed_formatting():
    report = SubtitleQA().validate([cue(1, 0, 2000, "Use <tag> as a word")])
    assert not any(
        finding.rule == "malformed_formatting_tag" for finding in report.findings
    )


def test_detects_malformed_ass_formatting_but_ignores_plain_braces():
    valid = SubtitleQA().validate([cue(1, 0, 2000, r"Text {literal} {\i1}italic{\i0}")])
    assert not any(
        finding.rule == "malformed_formatting_tag" for finding in valid.findings
    )

    malformed = SubtitleQA().validate([cue(1, 0, 2000, r"{\i1 incomplete")])
    assert any(
        finding.rule == "malformed_formatting_tag" for finding in malformed.findings
    )


def test_detects_empty_cues_empty_lines_and_malformed_formatting():
    report = SubtitleQA().validate(
        [cue(1, 0, 2000, ""), cue(2, 3000, 5000, "<i>unclosed\n\ntext")]
    )

    assert {finding.rule for finding in report.findings} >= {
        "empty_subtitle",
        "empty_line",
        "malformed_formatting_tag",
    }


def test_reports_non_monotonic_order_as_info():
    report = SubtitleQA().validate(
        [cue(1, 2000, 3000, "later"), cue(2, 0, 1000, "earlier")]
    )
    finding = next(
        item for item in report.findings if item.rule == "non_monotonic_order"
    )

    assert finding.severity == "info"
    assert report.passed


def test_detects_duplicate_or_invalid_cue_indices():
    report = SubtitleQA().validate(
        [
            cue(0, 0, 2000, "zero"),
            cue(2, 2000, 4000, "first"),
            cue(2, 4000, 6000, "second"),
        ]
    )
    assert {finding.rule for finding in report.findings} >= {
        "invalid_index",
        "duplicate_index",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_cps": 0},
        {"max_cps": float("inf")},
        {"max_cps": float("nan")},
        {"max_cps": True},
        {"max_characters_per_line": 0},
        {"max_lines": 1.5},
        {"min_duration_ms": True},
        {"min_duration_ms": -1},
        {"max_duration_ms": 0},
        {"min_duration_ms": 5000, "max_duration_ms": 1000},
    ],
)
def test_rejects_invalid_qa_thresholds(kwargs):
    with pytest.raises(ValueError):
        QARules(**kwargs)


@pytest.mark.parametrize(
    ("source", "file_format", "expected_rule", "severity"),
    [
        (
            "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello\n",
            "vtt",
            None,
            None,
        ),
        (
            "WEBVTT\n\n00:00:60.000 --> 00:01:02.000\nhello\n",
            "vtt",
            "invalid_timecode",
            "error",
        ),
        (
            "WEBVTT\n\nchapter-1\n00:00:00.000 --> 00:00:02.000\nhello\n",
            "vtt",
            None,
            None,
        ),
        (
            "[Script Info]\nTitle: test\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello\n",
            "ass",
            None,
            None,
        ),
        (
            "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:99:01.00,0:00:03.00,Default,,0,0,0,,Hello\n",
            "ass",
            "invalid_timecode",
            "error",
        ),
    ],
)
def test_source_format_rules_valid_and_invalid_boundaries(
    source, file_format, expected_rule, severity
):
    report = SubtitleQA().validate([], file_format, source)
    if expected_rule is None:
        assert not report.findings
    else:
        finding = next(item for item in report.findings if item.rule == expected_rule)
        assert finding.severity == severity


def test_custom_rule_can_be_composed_without_changing_qa_runner():
    class MarkerRule(SubtitleQARule):
        def validate(self, items, configured_rules, findings):
            findings.append(
                QAFinding("info", "custom_marker", items[0].index, "custom rule")
            )

    qa = SubtitleQA(rule_set=(*SubtitleQA.DEFAULT_RULES, MarkerRule()))
    report = qa.validate([cue(1, 0, 2000, "valid")])

    assert [finding.rule for finding in report.findings] == ["custom_marker"]


def test_many_cues_produce_stable_bounded_overlap_findings():
    items = [cue(index, 0, 10000, f"cue {index}") for index in range(1, 1501)]
    qa = SubtitleQA()
    first = qa.validate(items)
    second = qa.validate(items)
    overlap_findings = [
        finding for finding in first.findings if finding.rule == "overlap"
    ]

    assert len(overlap_findings) == len(items)
    assert [finding.to_dict() for finding in first.findings] == [
        finding.to_dict() for finding in second.findings
    ]
    assert len(first.findings) < len(items) * 5


def test_report_exposes_strict_policy_without_changing_default_policy():
    report = SubtitleQA().validate([cue(1, 0, 500, "short")])

    assert report.passed
    assert not report.strict_passed
    assert report.to_dict()["strict_passed"] is False


def test_finding_rejects_unknown_severity():
    with pytest.raises(ValueError):
        QAFinding("critical", "sample", 1, "invalid severity")
