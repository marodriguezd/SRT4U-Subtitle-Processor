import json
import os
import sqlite3

import pytest

from application.services.history_store import (
    SCHEMA_VERSION,
    HistoryError,
    HistoryStore,
    default_db_path,
    record_result_safely,
    record_safely,
)


def _db(tmp_path, name="history.db"):
    return str(tmp_path / name)


def test_creates_schema_with_version_and_indexes(tmp_path):
    path = _db(tmp_path)
    with HistoryStore(path) as store:
        version = store._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
        tables = {
            row[0]
            for row in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"runs", "qa_findings"} <= tables
        indexes = {
            row[0]
            for row in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "idx_runs_timestamp",
            "idx_runs_provider",
            "idx_qa_findings_run",
        } <= indexes


def test_record_and_read_run_with_nulls(tmp_path):
    with HistoryStore(_db(tmp_path)) as store:
        run_id = store.record_run("analyze", file_path="a.srt")
        row = store.get_run(run_id)
    assert row["operation"] == "analyze"
    assert row["file_path"] == "a.srt"
    assert row["success"] == 1
    assert row["provider"] is None
    assert row["estimated_cost"] is None
    assert row["timestamp"]


def test_record_run_rejects_bad_input(tmp_path):
    with HistoryStore(_db(tmp_path)) as store:
        with pytest.raises(HistoryError, match="operation"):
            store.record_run("")
        with pytest.raises(HistoryError, match="unknown run field"):
            store.record_run("process", api_key="secret")


def test_qa_findings_relation_and_limit(tmp_path):
    findings = [
        {
            "severity": "error",
            "rule": "invalid_timecode",
            "subtitle_index": 2,
            "message": "bad time",
            "metadata": {"a": 1},
        },
        {
            "severity": "warning",
            "rule": "overlap",
            "subtitle_index": 3,
            "message": "overlap",
            "metadata": {},
        },
    ]
    with HistoryStore(_db(tmp_path)) as store:
        run_id = store.record_run("qa", file_path="a.srt", qa_errors=1, qa_warnings=1)
        assert store.record_qa_findings(run_id, findings) == 2
        stored = store.get_findings(run_id)
        assert [item["rule"] for item in stored] == ["invalid_timecode", "overlap"]
        assert stored[0]["metadata"] == {"a": 1}
        assert store.get_findings(run_id + 999) == []
        assert store.get_run(run_id + 999) is None


def test_recent_runs_filters_and_order(tmp_path):
    with HistoryStore(_db(tmp_path)) as store:
        store.record_run("process", requested_provider="google", provider="google")
        store.record_run(
            "process",
            requested_provider="ollama",
            provider="google",
            fallback_used=1,
            providers_used=["ollama", "google"],
            fallback_error_type="network",
        )
        store.record_run(
            "benchmark",
            requested_provider="ollama",
            success=0,
            error_type="auth",
            benchmark_id="b1",
            run_index=0,
        )
        assert [row["id"] for row in store.recent_runs(limit=10)] == [3, 2, 1]
        assert len(store.recent_runs(limit=1)) == 1
        assert {row["id"] for row in store.recent_runs(provider="ollama")} == {2, 3}
        assert [row["id"] for row in store.recent_runs(operation="benchmark")] == [3]
        assert [row["id"] for row in store.recent_runs(only_errors=True)] == [3]
        assert [row["id"] for row in store.recent_runs(only_fallbacks=True)] == [2]
        assert store.recent_runs(provider="missing") == []


def test_recent_runs_date_range(tmp_path):
    with HistoryStore(_db(tmp_path)) as store:
        store.record_run("process", timestamp="2026-01-01T00:00:00+00:00")
        store.record_run("process", timestamp="2026-06-01T00:00:00+00:00")
        rows = store.recent_runs(since="2026-03-01T00:00:00+00:00")
        assert len(rows) == 1
        rows = store.recent_runs(until="2026-03-01T00:00:00+00:00")
        assert len(rows) == 1


def test_run_stats(tmp_path):
    with HistoryStore(_db(tmp_path)) as store:
        assert store.run_stats() == {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "fallbacks": 0,
            "avg_duration_ms": None,
            "min_duration_ms": None,
            "max_duration_ms": None,
        }
        store.record_run("process", duration_ms=100)
        store.record_run("process", duration_ms=300, success=0, error_type="x")
        store.record_run("process", duration_ms=200, fallback_used=1)
        stats = store.run_stats()
        assert stats["total"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["fallbacks"] == 1
        assert stats["avg_duration_ms"] == pytest.approx(200.0)
        assert stats["min_duration_ms"] == 100
        assert stats["max_duration_ms"] == 300


def test_queries_use_parameters_not_concatenation(tmp_path):
    with HistoryStore(_db(tmp_path)) as store:
        store.record_run("process", requested_provider="google")
        assert store.recent_runs(provider="x' OR '1'='1") == []
        assert store.run_stats(provider="x' OR '1'='1")["total"] == 0


def test_migrates_empty_legacy_database(tmp_path):
    path = _db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 0")
    conn.close()
    with HistoryStore(path) as store:
        assert store._version() == SCHEMA_VERSION
        run_id = store.record_run("process")
        assert store.get_run(run_id)["id"] == run_id


def test_refuses_newer_database(tmp_path):
    path = _db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(HistoryError, match="newer"):
        HistoryStore(path)


def test_corrupt_database_raises_history_error(tmp_path):
    path = _db(tmp_path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("not a database")
    with pytest.raises(HistoryError, match="cannot open"):
        HistoryStore(path)


def test_record_safely_never_raises(tmp_path):
    assert record_safely("process", file_path="a.srt") is not None
    # A directory is not a valid database: warning + None, no exception.
    assert record_safely("process", str(tmp_path), file_path="a.srt") is None
    assert record_result_safely(object(), operation="process") is not None


def test_default_path_respects_platform_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SRT4U_HISTORY_DB", str(tmp_path / "custom.db"))
    assert default_db_path() == str(tmp_path / "custom.db")
    monkeypatch.delenv("SRT4U_HISTORY_DB")
    assert default_db_path().endswith(os.path.join("SRT4U", "history.db"))


class _Stats:
    translation_failures = 2
    parse_issues = 1


class _Metrics:
    provider = "ollama"
    requested_provider = "ollama"
    model = "llama3"
    number_of_cues = 3
    characters_input = 30
    characters_output = 33
    words_input = 6
    words_output = 6
    duration_ms = 120
    success = True
    error_type = None
    retry_count = 1
    fallback_used = False
    providers_used = ["ollama"]
    input_tokens = 10
    output_tokens = 5
    total_tokens = 15
    estimated_cost = None


class _Finding:
    def __init__(self, severity, rule):
        self.severity = severity
        self.rule = rule
        self.subtitle_index = 1
        self.message = f"{rule} happened"
        self.metadata = {}


class _QAReport:
    findings = [_Finding("error", "invalid_timecode"), _Finding("warning", "overlap")]


class _Result:
    stats = _Stats()
    translation_metrics = _Metrics()
    qa_report = _QAReport()


def test_record_processing_result_end_to_end(tmp_path):
    with HistoryStore(_db(tmp_path)) as store:
        run_id = store.record_processing_result(
            _Result(),
            operation="process",
            file_path="movie.srt",
            file_format="srt",
            source_language="en",
            target_language="es",
            engine="openai",
        )
        row = store.get_run(run_id)
    assert row["provider"] == "ollama"
    assert row["requested_provider"] == "ollama"
    assert row["model"] == "llama3"
    assert row["number_of_cues"] == 3
    assert row["retry_count"] == 1
    assert row["providers_used"] == ["ollama"]
    assert row["total_tokens"] == 15
    assert row["translation_failures"] == 2
    assert row["parse_issues"] == 1
    assert row["qa_errors"] == 1
    assert row["qa_warnings"] == 1
    with HistoryStore(_db(tmp_path, "other.db")) as store:
        pass
    with HistoryStore(_db(tmp_path)) as store:
        assert [item["rule"] for item in store.get_findings(run_id)] == [
            "invalid_timecode",
            "overlap",
        ]


def test_record_processing_result_defaults_parse_issues_to_zero(tmp_path):
    """Schema v3: a result whose stats carry no parse_issues still records 0."""

    class _StatsNoIssues:
        translation_failures = 0

    class _ResultNoIssues:
        stats = _StatsNoIssues()
        translation_metrics = None
        qa_report = None

    with HistoryStore(_db(tmp_path)) as store:
        run_id = store.record_processing_result(
            _ResultNoIssues(), operation="process", file_path="clean.srt"
        )
        row = store.get_run(run_id)
    assert row["parse_issues"] == 0


def test_normal_process_records_parse_issue_count(tmp_path):
    """Regression (schema v3): normal ``process`` records the parse_issues
    count. A file with one unreadable block must land in history with
    ``parse_issues == 1`` (advisory; ``success`` stays 1)."""
    from application.services.history_store import record_result_safely
    from application.services.subtitle_service import SubtitleService

    source = tmp_path / "input.srt"
    source.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
        "2\n00:75:00,000 --> 00:75:01,000\nbad block\n",
        encoding="utf-8",
    )
    db = _db(tmp_path, "process.db")
    service = SubtitleService()
    result = service.process_subtitles(str(source), do_clean=False)
    assert result.stats.parse_issues == 1
    assert result.success
    record_result_safely(result, db_path=db, operation="process", file_path="input.srt")
    with HistoryStore(db) as store:
        row = store.recent_runs(operation="process")[0]
    assert row["parse_issues"] == 1
    assert row["success"] == 1


def test_record_benchmark_report(tmp_path):
    from application.services.translation_benchmark import BenchmarkRun

    runs = [
        BenchmarkRun(
            benchmark_id="b1",
            timestamp="2026-01-01T00:00:00+00:00",
            run_index=i,
            dataset_version="1",
            dataset_size=8,
            provider="fast",
            requested_provider="fast",
            model="fast-1",
            source_language="en",
            target_language="es",
            number_of_cues=8,
            characters_input=100,
            characters_output=110,
            words_input=20,
            words_output=20,
            duration_ms=50,
            success=True,
        )
        for i in range(3)
    ]
    with HistoryStore(_db(tmp_path)) as store:
        ids = store.record_benchmark_report(runs)
        assert len(ids) == 3
        assert len(store.recent_runs(operation="benchmark")) == 3
        row = store.get_run(ids[0])
        assert row["benchmark_id"] == "b1"
        assert row["run_index"] == 0


def test_export_rows_are_dataframe_ready(tmp_path):
    with HistoryStore(_db(tmp_path)) as store:
        store.record_run("process", requested_provider="google", duration_ms=10)
        rows = store.export_rows()
    assert isinstance(rows, list)
    assert rows[0]["requested_provider"] == "google"
    json.dumps(rows)


def test_cli_process_records_history(tmp_path, monkeypatch, capsys):
    import application.cli as cli

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
        translation_metrics = None
        qa_report = None

    class FakeSubtitleService:
        def process_subtitles(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr(cli, "SubtitleService", FakeSubtitleService)
    db = tmp_path / "cli.db"
    output = tmp_path / "output.srt"
    assert (
        cli.main(["process", str(source), "--output", str(output), "--db", str(db)])
        == 0
    )
    capsys.readouterr()
    with HistoryStore(str(db)) as store:
        rows = store.recent_runs()
    assert len(rows) == 1
    assert rows[0]["operation"] == "process"
    assert rows[0]["file_path"] == str(source)


def test_cli_history_commands(tmp_path, capsys):
    import application.cli as cli

    db = tmp_path / "history.db"
    with HistoryStore(str(db)) as store:
        store.record_run("process", file_path="a.srt", requested_provider="google")
        store.record_run(
            "process",
            file_path="b.srt",
            requested_provider="ollama",
            success=0,
            error_type="network",
        )

    assert cli.main(["history", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "a.srt" in out and "b.srt" in out

    assert cli.main(["history", "--db", str(db), "--provider", "ollama"]) == 0
    out = capsys.readouterr().out
    assert "b.srt" in out and "a.srt" not in out

    assert cli.main(["history", "--db", str(db), "--errors-only", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1 and payload[0]["error_type"] == "network"

    assert cli.main(["history", "--db", str(db), "--stats"]) == 0
    assert "1 fallidas" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cli.main(["history", "--db", str(db), "--limit", "0"])
    capsys.readouterr()


def test_cli_benchmark_store_and_qa_record(tmp_path, monkeypatch, capsys):
    import application.cli as cli
    from application.services.translation_providers import (
        ProviderRegistry,
        ProviderResponse,
        TranslationProvider,
    )

    class FakeProvider(TranslationProvider):
        name = "fake"
        model = "test-model"

        def translate(self, text, source_language, target_language, *, context=None):
            return "Hola"

        def translate_detailed(
            self, text, source_language, target_language, *, context=None
        ):
            return ProviderResponse("Hola", model=self.model)

    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: FakeProvider()
    )
    db = tmp_path / "history.db"
    assert (
        cli.main(
            [
                "benchmark",
                "--providers",
                "fake",
                "--runs",
                "1",
                "--db",
                str(db),
                "--store",
            ]
        )
        == 0
    )
    capsys.readouterr()
    with HistoryStore(str(db)) as store:
        rows = store.recent_runs(operation="benchmark")
    assert len(rows) == 1
    assert rows[0]["requested_provider"] == "fake"

    source = tmp_path / "input.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    assert cli.main(["qa", str(source)]) == 0
    capsys.readouterr()
    with HistoryStore(str(db)) as store:
        assert len(store.recent_runs(operation="qa")) == 1


def test_history_page_renders_recent_runs(qapp, tmp_path, monkeypatch):
    from application.ui.main_window import MainWindow

    monkeypatch.setenv("SRT4U_HISTORY_DB", str(tmp_path / "gui.db"))
    with HistoryStore(str(tmp_path / "gui.db")) as store:
        store.record_run("process", file_path="film.srt", requested_provider="google")
    window = MainWindow()
    try:
        window._switch_page(8)
        window._refresh_history()
        assert window.history_table.rowCount() == 1
        assert window.history_table.item(0, 2).text() == "process"
        assert window.lbl_history_empty.isVisible() is False
    finally:
        window.close()
