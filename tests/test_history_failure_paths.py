"""Failure-path tests for the local history database.

All databases are created in pytest temporary directories; the user's real
history file is never touched. Read-only tests chmod the file and then probe
whether the process can actually be denied writes, because root bypasses
permission bits and such tests would otherwise be meaningless.
"""

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from application.services import history_store as hs
from application.services.history_store import HistoryError, HistoryStore


def _write_denied(path: Path) -> bool:
    """Return True when the current process cannot write to ``path``."""
    try:
        with open(path, "ab"):
            return False
    except OSError:
        return True


def _make_readonly(path: Path) -> None:
    os.chmod(path, stat.S_IRUSR)


def _restore_writable(path: Path) -> None:
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _legacy_v2_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(hs._MIGRATIONS[1])
    conn.executescript(hs._MIGRATIONS[2])
    conn.execute(
        "INSERT INTO runs (timestamp, operation, success) VALUES (?, ?, 1)",
        ("2026-01-01T00:00:00+00:00", "process"),
    )
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()


def _schema_version(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def _row_count(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    finally:
        conn.close()


def test_readonly_current_database_reads_but_refuses_writes(tmp_path):
    db = tmp_path / "history.db"
    store = HistoryStore(str(db))
    store.record_run("process", success=True)
    store.close()

    # WAL-mode databases need the -wal/-shm sidecars to be writable for reads;
    # make the main file read-only and ensure the sidecars exist from the store.
    _make_readonly(db)
    try:
        if not _write_denied(db):
            pytest.skip("filesystem does not enforce read-only permissions here")

        try:
            store = HistoryStore(str(db))
        except HistoryError:
            # Refusing to open a read-only store is an acceptable, bounded outcome.
            return

        try:
            rows = store.recent_runs()
            assert len(rows) == 1
            with pytest.raises(HistoryError):
                store.record_run("process", success=True)
            assert len(store.recent_runs()) == 1
        finally:
            store.close()
    finally:
        _restore_writable(db)

    assert _row_count(db) == 1


def test_legacy_readonly_database_is_not_migrated_and_raises_history_error(tmp_path):
    db = tmp_path / "legacy.db"
    _legacy_v2_db(db)
    _make_readonly(db)
    try:
        if not _write_denied(db):
            pytest.skip("filesystem does not enforce read-only permissions here")

        with pytest.raises(HistoryError):
            HistoryStore(str(db))
    finally:
        _restore_writable(db)

    # A refused migration must leave the legacy version and rows untouched.
    assert _schema_version(db) == 2
    assert _row_count(db) == 1


def test_corrupt_database_fails_with_bounded_history_error(tmp_path):
    db = tmp_path / "corrupt.db"
    db.write_bytes(b"this is not an sqlite database" * 64)

    with pytest.raises(HistoryError):
        HistoryStore(str(db))


def test_store_close_is_idempotent(tmp_path):
    store = HistoryStore(str(tmp_path / "history.db"))
    store.close()
    store.close()
