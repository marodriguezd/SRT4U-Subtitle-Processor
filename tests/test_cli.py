import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def run_cli(*args, config_home):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_home)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "application.cli", "process", *map(str, args)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_import_does_not_import_pyqt6():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import application.cli; "
            "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
            "for name in sys.modules)",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cli_cleans_and_converts_one_file(tmp_path):
    output = tmp_path / "cleaned.vtt"
    result = run_cli(
        FIXTURES_DIR / "sample.srt",
        "--output",
        output,
        "--clean",
        "--format",
        "vtt",
        config_home=tmp_path / "config",
    )

    assert result.returncode == 0, result.stderr
    content = output.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "AnimeFansubPro" not in content
    assert "OK " in result.stdout


def test_cli_processes_batch_and_preserves_relative_paths(tmp_path):
    input_dir = tmp_path / "input"
    nested_dir = input_dir / "nested"
    nested_dir.mkdir(parents=True)
    (input_dir / "one.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nFirst\n", encoding="utf-8"
    )
    (nested_dir / "two.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:01.000\nSecond\n", encoding="utf-8"
    )
    output_dir = tmp_path / "output"

    result = run_cli(
        input_dir,
        "--output",
        output_dir,
        config_home=tmp_path / "config",
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "one.srt").exists()
    assert (output_dir / "nested" / "two.vtt").exists()
    assert "2/2 archivos procesados" in result.stdout


def test_cli_uses_json_pipeline_and_cli_overrides_preset(tmp_path):
    preset = tmp_path / "pipeline.json"
    preset.write_text(
        json.dumps({"pipeline": {"clean": True, "target_format": "srt"}}),
        encoding="utf-8",
    )
    output = tmp_path / "result.vtt"

    result = run_cli(
        FIXTURES_DIR / "sample.srt",
        "--config",
        preset,
        "--format",
        "vtt",
        "--output",
        output,
        config_home=tmp_path / "config",
    )

    assert result.returncode == 0, result.stderr
    content = output.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "AnimeFansubPro" not in content


def test_cli_rejects_invalid_presets(tmp_path):
    preset = tmp_path / "pipeline.json"
    preset.write_text(
        json.dumps(
            {"pipeline": {"translate": True, "target_language": "es", "qa": True}}
        ),
        encoding="utf-8",
    )

    result = run_cli(
        FIXTURES_DIR / "sample.srt",
        "--config",
        preset,
        config_home=tmp_path / "config",
    )

    assert result.returncode == 2
    assert "opciones desconocidas" in result.stderr


def test_cli_requires_target_when_translation_enabled(tmp_path):
    result = run_cli(
        FIXTURES_DIR / "sample.srt",
        "--translate",
        config_home=tmp_path / "config",
    )

    assert result.returncode == 2
    assert "--target es obligatorio" in result.stderr


def test_cli_stats_is_opt_in_and_preserves_default_output(
    tmp_path, monkeypatch, capsys
):
    import application.cli as cli

    source = tmp_path / "input.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")

    from application.services.translation_models import TranslationMetrics

    class FakeStats:
        processed_items_count = 1
        elapsed_time = 0.01
        translation_failures = 0

    class FakeResult:
        stats = FakeStats()
        output_content = "translated"
        # ``ProcessingResult`` contract (deep-audit H1/M7): parse issues are
        # surfaced to the user instead of being dropped silently.
        parse_issues = []
        translation_metrics = TranslationMetrics.for_text(
            provider="google",
            model=None,
            source_language="auto",
            target_language="es",
            source_text="Hello",
            translated_text="Hola",
            duration_ms=15,
            success=True,
        )

    class FakeSubtitleService:
        def process_subtitles(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr(cli, "SubtitleService", FakeSubtitleService)
    output = tmp_path / "output.srt"
    assert cli.main(["process", str(source), "--output", str(output)]) == 0
    default_output = capsys.readouterr().out
    assert "Provider:" not in default_output

    assert cli.main(["process", str(source), "--output", str(output), "--stats"]) == 0
    stats_output = capsys.readouterr().out
    assert "Provider: google" in stats_output
    assert "Duration: 15ms" in stats_output
    assert "Status: success" in stats_output


def test_cli_translation_reuses_service_and_resolves_ollama_alias(
    tmp_path, monkeypatch
):
    import application.cli as cli

    source = tmp_path / "input.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    captured = {}

    class FakeStats:
        processed_items_count = 1
        elapsed_time = 0.01
        translation_failures = 0

    class FakeResult:
        stats = FakeStats()
        output_content = "translated"
        # ``ProcessingResult`` contract (deep-audit H1/M7): parse issues are
        # surfaced to the user instead of being dropped silently.
        parse_issues = []

    class FakeSubtitleService:
        def process_subtitles(self, **kwargs):
            captured.update(kwargs)
            return FakeResult()

    monkeypatch.setattr(cli, "SubtitleService", FakeSubtitleService)
    output = tmp_path / "translated.srt"

    exit_code = cli.main(
        [
            "process",
            str(source),
            "--output",
            str(output),
            "--translate",
            "--target",
            "es",
            "--engine",
            "ollama",
        ]
    )

    assert exit_code == 0
    assert captured["do_translate"] is True
    assert captured["target_language"] == "es"
    # Single source of truth: the CLI passes "ollama" through and the
    # ProviderRegistry alias resolves it; requested identity is preserved.
    assert captured["engine"] == "ollama"
    assert output.read_text(encoding="utf-8") == "translated"


def test_cli_stats_json_emits_structured_metrics(tmp_path, monkeypatch, capsys):
    import json as json_module

    import application.cli as cli
    from application.services.translation_models import TranslationMetrics

    source = tmp_path / "input.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")

    class FakeStats:
        processed_items_count = 1
        elapsed_time = 0.01
        translation_failures = 0

    class FakeResult:
        stats = FakeStats()
        output_content = "translated"
        # ``ProcessingResult`` contract (deep-audit H1/M7): parse issues are
        # surfaced to the user instead of being dropped silently.
        parse_issues = []
        translation_metrics = TranslationMetrics.for_text(
            provider="ollama",
            model="llama3",
            source_language="auto",
            target_language="es",
            source_text="Hello",
            translated_text="Hola",
            duration_ms=15,
            success=True,
            requested_provider="ollama",
            providers_used=["ollama"],
        )

    class FakeSubtitleService:
        def process_subtitles(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr(cli, "SubtitleService", FakeSubtitleService)
    output = tmp_path / "output.srt"
    assert (
        cli.main(["process", str(source), "--output", str(output), "--stats-json"]) == 0
    )
    lines = capsys.readouterr().out.splitlines()
    json_lines = [line for line in lines if line.strip().startswith("{")]
    assert len(json_lines) == 1
    payload = json_module.loads(json_lines[0])
    assert payload["requested_provider"] == "ollama"
    assert payload["provider"] == "ollama"
    assert payload["model"] == "llama3"


def test_cli_does_not_overwrite_input_file(tmp_path):
    source = tmp_path / "input.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nKeep me\n", encoding="utf-8")
    hardlink = tmp_path / "alias.srt"
    try:
        os.link(source, hardlink)
    except OSError as exc:
        pytest.skip(f"hard links are unavailable: {exc}")

    result = run_cli(
        source,
        "--output",
        hardlink,
        config_home=tmp_path / "config",
    )

    assert result.returncode == 2
    assert "no puede sobrescribir" in result.stderr
    assert "Keep me" in source.read_text(encoding="utf-8")
