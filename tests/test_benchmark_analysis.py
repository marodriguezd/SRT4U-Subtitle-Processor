import json

import pytest

from analysis.benchmark_analysis import (
    clean_runs,
    data_quality,
    describe,
    error_summary,
    load_report,
    load_runs_csv,
    run_analysis,
    size_relationship,
    validate_runs,
)


def _row(provider, **overrides):
    row = {
        "benchmark_id": "abc",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "run_index": 0,
        "dataset_version": "1",
        "dataset_size": 4,
        "provider": provider,
        "requested_provider": provider,
        "model": f"{provider}-1",
        "source_language": "en",
        "target_language": "es",
        "number_of_cues": 4,
        "characters_input": 40,
        "characters_output": 44,
        "words_input": 8,
        "words_output": 8,
        "duration_ms": 1000,
        "success": True,
        "error_type": None,
        "retry_count": 0,
        "fallback_used": False,
        "providers_used": [provider],
        "fallback_error_type": None,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "estimated_cost": None,
        "cues_per_second": 4.0,
        "characters_per_second": 40.0,
        "words_per_second": 8.0,
        "latency_per_cue_ms": 250.0,
        "latency_per_1k_chars_ms": 25000.0,
    }
    row.update(overrides)
    return row


def test_clean_runs_coerces_csv_strings_and_preserves_failures():
    rows, notes = clean_runs(
        [
            {
                "requested_provider": "a",
                "success": "True",
                "duration_ms": "1000",
                "retry_count": "2",
                "fallback_used": "False",
                "providers_used": '["a"]',
                "number_of_cues": "4",
            },
            _row("b", success=False, error_type="network", duration_ms=500),
            "not-a-mapping",
        ]
    )
    assert len(rows) == 2
    assert rows[0]["duration_ms"] == 1000
    assert rows[0]["success"] is True
    assert rows[0]["providers_used"] == ["a"]
    assert rows[1]["success"] is False
    assert any("dropped 1" in note for note in notes)


def test_describe_computes_stats_per_provider():
    rows = [
        _row("a", run_index=0, duration_ms=1000, latency_per_cue_ms=250.0),
        _row("a", run_index=1, duration_ms=2000, latency_per_cue_ms=500.0),
        _row("b", run_index=0, duration_ms=500, latency_per_cue_ms=125.0),
        _row("b", run_index=1, success=False, error_type="timeout", duration_ms=500),
    ]
    summary = describe(rows)
    by_group = {entry["group"]: entry for entry in summary}
    assert by_group["a"]["n_total"] == 2
    assert by_group["a"]["duration_ms.mean"] == pytest.approx(1500.0)
    assert by_group["a"]["duration_ms.median"] == pytest.approx(1500.0)
    assert by_group["a"]["duration_ms.min"] == 1000
    assert by_group["a"]["duration_ms.max"] == 2000
    assert by_group["a"]["duration_ms.stdev"] == pytest.approx(707.106, rel=1e-3)
    assert by_group["a"]["duration_ms.iqr"] == pytest.approx(1500.0)
    assert by_group["b"]["n_success"] == 1
    assert by_group["b"]["n_failed"] == 1
    assert by_group["b"]["duration_ms.count"] == 1
    assert by_group["b"]["duration_ms.stdev"] is None


def test_error_summary_rates_and_types():
    rows = [
        _row("a"),
        _row("a", success=False, error_type="network", retry_count=2),
        _row("a", success=False, error_type="network", retry_count=1),
        _row(
            "a",
            success=False,
            error_type="auth",
            fallback_used=True,
            providers_used=["a", "b"],
            fallback_error_type="auth",
        ),
    ]
    summary = error_summary(rows)
    assert len(summary) == 1
    entry = summary[0]
    assert entry["success_rate"] == pytest.approx(0.25)
    assert entry["failure_rate"] == pytest.approx(0.75)
    assert entry["error_types"] == {"network": 2, "auth": 1}
    assert entry["retry_mean"] == pytest.approx(0.75)
    assert entry["retry_max"] == 2
    assert entry["fallback_used_count"] == 1
    assert entry["fallback_rate"] == pytest.approx(0.25)


def test_size_relationship_perfect_correlation():
    rows = [
        _row(
            "a",
            characters_input=10 * (i + 1),
            duration_ms=100 * (i + 1),
            words_input=2 * (i + 1),
        )
        for i in range(5)
    ]
    result = size_relationship(rows)
    assert result["n_successful"] == 5
    assert result["pearson"]["chars_in_vs_duration"] == pytest.approx(1.0)
    assert result["pearson"]["words_in_vs_duration"] == pytest.approx(1.0)


def test_size_relationship_needs_two_points():
    result = size_relationship([_row("a")])
    assert result["n_successful"] == 1
    assert result["pearson"]["chars_in_vs_duration"] is None


def test_validate_runs_detects_problems():
    rows = [
        _row("a", run_index=0),
        _row("a", run_index=2),
        _row("b", run_index=0, duration_ms=-5),
        _row("b", run_index=1, success=True, error_type="network"),
    ]
    report = validate_runs(rows)
    assert report["row_count"] == 4
    assert report["failed_runs"] == 0
    assert report["providers"] == {"a": 2, "b": 2}
    assert len(report["impossible_values"]) == 2
    assert report["incomplete_run_sequences"] == {"a": [0, 2]}


def test_data_quality_flags_expected_gaps():
    rows = [
        _row("a", run_index=0, model=None),
        _row(
            "a",
            run_index=1,
            fallback_used=True,
            providers_used=["a", "b"],
            fallback_error_type="network",
        ),
    ]
    findings = {item["check"]: item for item in data_quality(rows)}
    assert findings["fallback_runs"]["count"] == 1
    assert findings["missing_tokens"]["count"] == 2
    assert findings["null_estimated_cost"]["count"] == 2
    assert findings["missing_model"]["count"] == 1
    assert findings["small_samples"]["count"] == 1
    assert findings["impossible_values"]["count"] == 0


def test_run_analysis_writes_artifacts_without_plots(tmp_path):
    report = {
        "benchmark_id": "abc",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "dataset_version": "1",
        "dataset_size": 4,
        "config": {
            "providers": ["a"],
            "runs": 2,
            "source_language": "en",
            "target_language": "es",
        },
        "environment": {"python": "3.14", "platform": "test"},
        "runs": [_row("a", run_index=0), _row("a", run_index=1)],
    }
    payload = run_analysis(report, str(tmp_path), include_plots=False)

    assert (tmp_path / "summary.csv").exists()
    assert (tmp_path / "cleaned_dataset.csv").exists()
    assert (tmp_path / "analysis_report.json").exists()
    assert payload["plots"] == {}
    assert payload["validation"]["row_count"] == 2
    assert len(payload["conclusions"]) >= 1
    assert "dataset v1" in payload["conclusions"][0]
    stored = json.loads((tmp_path / "analysis_report.json").read_text())
    assert stored["benchmark_id"] == "abc"
    assert len(stored["descriptive_by_provider"]) == 1


def test_run_analysis_conclusions_never_crown_a_winner(tmp_path):
    report = {
        "benchmark_id": "abc",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "dataset_version": "1",
        "dataset_size": 4,
        "config": {
            "providers": ["a", "b"],
            "runs": 1,
            "source_language": "en",
            "target_language": "es",
        },
        "environment": {},
        "runs": [
            _row("a", latency_per_cue_ms=100.0, duration_ms=400),
            _row(
                "b",
                latency_per_cue_ms=200.0,
                duration_ms=800,
                success=False,
                error_type="network",
            ),
        ],
    }
    payload = run_analysis(report, str(tmp_path), include_plots=False)
    text = " ".join(payload["conclusions"]).lower()
    assert "winner" not in text
    assert "best" not in text or "lowest median" in text
    assert any("failed" in line for line in payload["conclusions"])


def test_load_report_and_csv_roundtrip(tmp_path):
    from application.services.translation_benchmark import (
        BenchmarkConfig,
        TranslationBenchmark,
    )

    sample = load_report("analysis/sample_benchmark.json")
    assert sample["dataset_version"] == "1"
    assert len(sample["runs"]) == 20

    rows = load_runs_csv("analysis/sample_benchmark.csv")
    assert len(rows) == 20
    assert rows[0]["duration_ms"] == int(rows[0]["duration_ms"])
    assert isinstance(rows[0]["success"], bool)

    assert BenchmarkConfig is not None
    assert TranslationBenchmark is not None
    _ = (tmp_path,)


def test_sample_dataset_reports_fallback_and_variability():
    sample = load_report("analysis/sample_benchmark.json")
    rows, _ = clean_runs(sample["runs"])
    errors = {entry["group"]: entry for entry in error_summary(rows)}
    assert errors["flaky-stub"]["fallback_rate"] == pytest.approx(1.0)
    summary = {entry["group"]: entry for entry in describe(rows)}
    assert (
        summary["slow-stub"]["latency_per_cue_ms.median"]
        > summary["fast-stub"]["latency_per_cue_ms.median"]
    )
