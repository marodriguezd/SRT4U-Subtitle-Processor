import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(command, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    config_dir = Path(gettempdir()) / "srt4u-cli-analytics-test-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    env["XDG_CONFIG_HOME"] = str(config_dir)
    return subprocess.run(
        [sys.executable, "-m", "application.cli", command, *map(str, args)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_analyze_prints_human_readable_metrics():
    result = run_cli("analyze", "tests/fixtures/sample.srt")

    assert result.returncode == 0
    assert "Subtítulos: 5" in result.stdout
    assert "CPS medio/máx/mín:" in result.stdout
    assert result.stderr == ""


def test_cli_analyze_json_is_valid_machine_readable_output():
    result = run_cli("analyze", "tests/fixtures/sample.srt", "--json")

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert set(data) == {"analytics", "qa"}
    assert data["analytics"]["content"]["subtitle_count"] == 5
    assert "findings" in data["qa"]
    assert result.stderr == ""


def test_cli_qa_json_contains_structured_findings(tmp_path):
    source = tmp_path / "issues.srt"
    source.write_text(
        "1\n00:00:00,000 --> 00:00:00,500\nvery long line to test\n\n"
        "2\n00:00:00,300 --> 00:00:01,000\nvery long line to test\n",
        encoding="utf-8",
    )
    result = run_cli("qa", source, "--json")

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["passed"] is True
    assert report["warning_count"] > 0
    assert any(finding["rule"] == "overlap" for finding in report["findings"])
    assert all(
        {"severity", "rule", "subtitle_index", "message", "metadata"} <= set(finding)
        for finding in report["findings"]
    )


def test_cli_qa_returns_nonzero_on_invalid_timecodes(tmp_path):
    source = tmp_path / "bad.srt"
    source.write_text("1\nmalformed\nBroken\n", encoding="utf-8")
    result = run_cli("qa", source, "--json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["passed"] is False
    assert report["error_count"] == 1


def test_cli_qa_strict_fails_on_warnings_and_default_still_passes(tmp_path):
    source = tmp_path / "warning.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:00,500\nShort\n", encoding="utf-8")
    default_result = run_cli("qa", source, "--json")
    strict_result = run_cli("qa", source, "--strict", "--json")

    assert default_result.returncode == 0
    assert json.loads(default_result.stdout)["passed"] is True
    assert strict_result.returncode == 1
    strict_report = json.loads(strict_result.stdout)
    assert strict_report["strict_passed"] is False
    assert strict_report["warning_count"] > 0


def test_cli_qa_reports_missing_file_with_exit_code_two(tmp_path):
    result = run_cli("qa", tmp_path / "no-such-file.srt", "--json")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "archivo no encontrado" in result.stderr


def test_cli_qa_strict_passes_without_warnings_or_errors(tmp_path):
    source = tmp_path / "valid.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    result = run_cli("qa", source, "--strict", "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["strict_passed"] is True
    assert json.loads(result.stdout)["warning_count"] == 0


def test_cli_qa_human_strict_summary_marks_warning_failure(tmp_path):
    source = tmp_path / "warning.srt"
    source.write_text("1\\n00:00:00,000 --> 00:00:00,500\\nShort\\n", encoding="utf-8")
    result = run_cli("qa", source, "--strict")
    assert result.returncode == 1
    assert "QA: problemas encontrados" in result.stdout


def test_cli_qa_csv_flag_and_json_csv_conflict(tmp_path):
    source = PROJECT_ROOT / "tests/fixtures/sample.srt"
    result = run_cli("qa", source, "--csv")
    assert result.returncode == 0
    assert "severity,rule,subtitle_index,message,metadata" in result.stdout
    empty_source = tmp_path / "empty.srt"
    empty_source.write_text("", encoding="utf-8")
    empty_csv = run_cli("qa", empty_source, "--csv")
    assert empty_csv.returncode == 0
    assert empty_csv.stdout.startswith("severity,rule,subtitle_index,message,metadata")
    assert "warning,empty_file,," in empty_csv.stdout

    conflict = run_cli("qa", source, "--json", "--csv")
    assert conflict.returncode == 2
    assert "--json y --format csv" in conflict.stderr


def test_cli_rejects_output_extension_that_conflicts_with_requested_format(tmp_path):
    result = run_cli(
        "qa",
        "tests/fixtures/sample.srt",
        "--format",
        "json",
        "--output",
        tmp_path / "report.csv",
    )
    assert result.returncode == 2
    assert "extensión de --output" in result.stderr


def test_cli_rejects_strict_for_analyze():
    result = run_cli("analyze", "tests/fixtures/sample.srt", "--strict")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_cli_exports_json_and_csv_files(tmp_path):
    source = PROJECT_ROOT / "tests/fixtures/sample.srt"
    json_path = tmp_path / "report.json"
    json_result = run_cli("analyze", source, "--output", json_path)
    assert json_result.returncode == 0
    assert (
        json.loads(json_path.read_text(encoding="utf-8"))["analytics"]["content"][
            "subtitle_count"
        ]
        == 5
    )

    csv_path = tmp_path / "report.csv"
    csv_result = run_cli("qa", source, "--output", csv_path)
    assert csv_result.returncode == 0
    assert "severity,rule,subtitle_index,message,metadata" in csv_path.read_text(
        encoding="utf-8"
    )

    explicit_csv_path = tmp_path / "explicit.csv"
    explicit_csv_result = run_cli("qa", source, "--csv", "--output", explicit_csv_path)
    assert explicit_csv_result.returncode == 0
    assert explicit_csv_path.read_text(encoding="utf-8").startswith(
        "severity,rule,subtitle_index,message,metadata"
    )


def test_cli_reports_missing_file_cleanly():
    with TemporaryDirectory() as temp_dir:
        missing = Path(temp_dir) / "no-such-subtitle.srt"
        result = run_cli("analyze", missing, "--json")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "no se pudo analizar" in result.stderr


def test_cli_rejects_invalid_export_format():
    result = run_cli("analyze", "tests/fixtures/sample.srt", "--format", "xml")

    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def test_cli_rejects_json_and_csv_combination():
    result = run_cli(
        "analyze", "tests/fixtures/sample.srt", "--json", "--format", "csv"
    )

    assert result.returncode == 2
    assert "--json y --format csv" in result.stderr


def test_cli_analytics_modules_and_commands_are_headless():
    code = (
        "import sys; from application.services.subtitle_analytics import SubtitleAnalyticsService; "
        "from application.services.subtitle_qa import SubtitleQA; import application.cli; "
        "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') for name in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
