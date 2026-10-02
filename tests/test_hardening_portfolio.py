"""Portfolio-hardening regressions: concurrency, persistence, caps, identity, CI.

Small, deterministic, offline. Each test guards a contract documented in
``docs/``/``AGENTS.md`` that the functional suite did not pin before.
"""

import re
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------- JobManager concurrency ---


def test_job_manager_concurrent_submit_get_cancel_list_is_safe():
    """Concurrent submit/get/cancel/list must not deadlock or corrupt state."""
    from application.api.jobs import JobManager

    manager = JobManager(max_workers=4, max_jobs=50)
    errors = []

    try:
        job_ids = [
            manager.submit("t", lambda: time.sleep(0.01) or "ok") for _ in range(20)
        ]

        def worker():
            try:
                for _ in range(100):
                    manager.get(job_ids[0])
                    manager.list(limit=10)
            except Exception as exc:  # pragma: no cover - must never happen
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for job_id in job_ids[5:10]:
            manager.cancel(job_id)
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive(), "job-manager access deadlocked"

        assert not errors, errors
        # Every id is either still tracked (terminal) or pruned — never corrupt.
        for job_id in job_ids:
            job = manager.get(job_id)
            if job is not None:
                assert job["status"] in {
                    "queued",
                    "running",
                    "completed",
                    "failed",
                    "cancelled",
                }
    finally:
        manager.shutdown()


def test_job_manager_running_cancel_discards_result():
    """Best-effort contract: a running job finishes, its result is discarded."""
    from application.api.jobs import JobManager

    release = threading.Event()
    manager = JobManager(max_workers=1)
    try:
        job_id = manager.submit("t", lambda: release.wait(5) or {"secret": "payload"})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if manager.get(job_id)["status"] == "running":
                break
            time.sleep(0.01)
        assert manager.get(job_id)["status"] == "running"
        assert manager.cancel(job_id) == "running"
        release.set()
        final = manager.wait_for(job_id, timeout=10)
        assert final["status"] == "cancelled"
        assert final["result"] is None
    finally:
        release.set()
        manager.shutdown()


# ------------------------------------------------- History migrations -------


def _legacy_v1_db(path: Path) -> None:
    """Create a v1 database (no media_duration_ms, no parse_issues)."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " timestamp TEXT NOT NULL, operation TEXT NOT NULL, file_path TEXT,"
        " success INTEGER NOT NULL DEFAULT 1)"
    )
    conn.execute(
        "CREATE TABLE qa_findings (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,"
        " severity TEXT NOT NULL, rule TEXT NOT NULL,"
        " subtitle_index INTEGER, message TEXT NOT NULL, metadata TEXT)"
    )
    conn.execute(
        "INSERT INTO runs (timestamp, operation, file_path, success)"
        " VALUES ('2026-01-01T00:00:00+00:00', 'process', 'a.srt', 1)"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


def test_history_migrates_v1_to_v3_without_losing_rows(tmp_path):
    from application.services.history_store import HistoryStore

    db = tmp_path / "legacy.db"
    _legacy_v1_db(db)
    with HistoryStore(str(db)) as store:
        assert store._version() == 3
        rows = store.recent_runs(limit=10)
        assert len(rows) == 1
        assert rows[0]["file_path"] == "a.srt"
        # New columns exist and default to NULL/0, old data intact.
        assert "media_duration_ms" in rows[0]
        assert "parse_issues" in rows[0]


def test_history_schema_has_no_secret_columns(tmp_path):
    """The schema must offer nowhere to store texts, media or secrets."""
    from application.services.history_store import HistoryStore

    with HistoryStore(str(tmp_path / "h.db")) as store:
        cols = {
            row[1] for row in store._conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        finding_cols = {
            row[1]
            for row in store._conn.execute("PRAGMA table_info(qa_findings)").fetchall()
        }
    forbidden = {
        "subtitle_text",
        "transcript",
        "content",
        "audio",
        "video",
        "api_key",
        "secret",
        "token",
        "password",
        "header",
    }
    assert not (forbidden & {col.lower() for col in cols | finding_cols}), cols


def test_history_unknown_field_rejected_not_silently_stored(tmp_path):
    """Unknown run fields raise HistoryError (distinct from empty results)."""
    from application.services.history_store import HistoryError, HistoryStore

    with HistoryStore(str(tmp_path / "h.db")) as store:
        try:
            store.record_run("process", subtitle_text="should never persist")
        except HistoryError:
            pass
        else:  # pragma: no cover - contract violation
            raise AssertionError("unknown field must be rejected")
        assert store.recent_runs(limit=10) == []


# ------------------------------------------------- Config persistence ------


def test_config_corrupt_json_falls_back_to_defaults(tmp_path, monkeypatch):
    from application.services.config_service import ConfigService

    config_dir = tmp_path / "SRT4U"
    config_dir.mkdir(parents=True, exist_ok=True)
    settings = config_dir / "settings.json"
    settings.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(ConfigService, "_get_config_dir", lambda self: str(config_dir))
    service = ConfigService()
    assert service.load_error is not None
    assert service.get("target_lang") == ConfigService.DEFAULT_CONFIG["target_lang"]
    # Saving again must produce valid JSON (atomic write, no truncation).
    assert service.save() is True
    import json

    assert (
        json.loads(settings.read_text(encoding="utf-8"))["target_lang"]
        == (ConfigService.DEFAULT_CONFIG["target_lang"])
    )


# ------------------------------------------------- Upload caps -------------


def test_upload_caps_are_centralized_and_distinct():
    from application.api import deps as api_deps
    from application.api.routes import transcribe as transcribe_route

    assert api_deps.MAX_UPLOAD_BYTES == 5 * 1024 * 1024
    assert transcribe_route.TRANSCRIBE_MAX_BYTES == 500 * 1024 * 1024
    assert transcribe_route.TRANSCRIBE_MAX_BYTES > api_deps.MAX_UPLOAD_BYTES


# ------------------------------------------------- About single source ----


def test_about_identity_has_single_source():
    from application import version as version_module

    assert version_module.APP_GITHUB_OWNER == "marodriguezd"
    assert version_module.APP_GITHUB_REPO == "SRT4U-Subtitle-Processor"
    assert version_module.APP_GITHUB_PROFILE_URL.endswith(
        version_module.APP_GITHUB_OWNER
    )
    assert version_module.APP_GITHUB_REPO_URL.endswith(
        f"{version_module.APP_GITHUB_OWNER}/{version_module.APP_GITHUB_REPO}"
    )
    assert " " in version_module.APP_AUTHOR_NAME  # real display name, not a handle
    source = (ROOT / "application" / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert "APP_GITHUB_PROFILE_URL" in source
    assert "APP_GITHUB_REPO_URL" in source
    assert "APP_AUTHOR_NAME" in source


# ------------------------------------------------- Supply chain ------------


def test_ci_actions_are_pinned_to_shas():
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(
        encoding="utf-8"
    )
    # No floating `uses: owner/action@vN` may remain; every pin keeps a readable
    # `# vN[.N]` comment so reviewers still see the intended release.
    for match in re.finditer(r"uses:\s*(\S+)", workflow):
        ref = match.group(1)
        assert re.match(r"^[^@]+@[0-9a-f]{40}$", ref), f"unpinned action: {ref}"
    assert workflow.count("# v") >= 5
    assert "contents: read" in workflow
    assert workflow.count("contents: write") == 1


def test_dependabot_covers_actions_and_pip():
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert "github-actions" in config
    assert "pip" in config
    assert "weekly" in config


def test_coverage_floor_is_configured_and_realistic():
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)
    assert "pytest-cov" in " ".join(project["project"]["optional-dependencies"]["dev"])
    floor = project["tool"]["coverage"]["report"]["fail_under"]
    assert 50 <= floor <= 85, floor  # honest floor for a GUI+headless suite
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(
        encoding="utf-8"
    )
    assert "--cov-fail-under" in workflow
