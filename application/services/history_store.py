"""Local SQLite history of SRT4U executions (processing, QA, transcription,
benchmarks).

Auxiliary capability: recording must never break processing, translation, or
the UI. No subtitle texts, API keys, headers, secrets, audio, or video are
persisted — only aggregate metrics, QA finding metadata, and file identity.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..logging_setup import get_logger

logger = get_logger("history")

#: Current schema revision. ``_MIGRATIONS`` maps version -> DDL applied once.
SCHEMA_VERSION = 2

_MIGRATIONS = {
    1: """
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        operation TEXT NOT NULL,
        file_path TEXT,
        file_format TEXT,
        source_language TEXT,
        target_language TEXT,
        provider TEXT,
        requested_provider TEXT,
        model TEXT,
        number_of_cues INTEGER,
        characters_input INTEGER,
        characters_output INTEGER,
        words_input INTEGER,
        words_output INTEGER,
        duration_ms INTEGER,
        success INTEGER NOT NULL DEFAULT 1,
        error_type TEXT,
        retry_count INTEGER DEFAULT 0,
        fallback_used INTEGER DEFAULT 0,
        providers_used TEXT,
        fallback_error_type TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        total_tokens INTEGER,
        estimated_cost REAL,
        qa_errors INTEGER DEFAULT 0,
        qa_warnings INTEGER DEFAULT 0,
        translation_failures INTEGER DEFAULT 0,
        benchmark_id TEXT,
        run_index INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_runs_provider ON runs(requested_provider);
    CREATE INDEX IF NOT EXISTS idx_runs_operation ON runs(operation);
    CREATE INDEX IF NOT EXISTS idx_runs_benchmark ON runs(benchmark_id);
    CREATE TABLE IF NOT EXISTS qa_findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        severity TEXT NOT NULL,
        rule TEXT NOT NULL,
        subtitle_index INTEGER,
        message TEXT NOT NULL,
        metadata TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_qa_findings_run ON qa_findings(run_id);
    """,
    2: """
    ALTER TABLE runs ADD COLUMN media_duration_ms INTEGER;
    """,
}

_RUN_COLUMNS = (
    "timestamp",
    "operation",
    "file_path",
    "file_format",
    "source_language",
    "target_language",
    "provider",
    "requested_provider",
    "model",
    "number_of_cues",
    "characters_input",
    "characters_output",
    "words_input",
    "words_output",
    "duration_ms",
    "success",
    "error_type",
    "retry_count",
    "fallback_used",
    "providers_used",
    "fallback_error_type",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost",
    "qa_errors",
    "qa_warnings",
    "translation_failures",
    "benchmark_id",
    "run_index",
    "media_duration_ms",
)


class HistoryError(Exception):
    """Raised for history-store failures; never carries secrets."""


def _split_statements(ddl: str):
    """Split a migration script into individual statements.

    ``executescript`` cannot be used inside an explicit transaction because it
    issues an implicit COMMIT first; executing the statements one by one keeps
    the whole migration atomic. All migrations in this module use simple
    ``;``-terminated statements with no embedded semicolons in string literals.
    """
    for chunk in ddl.split(";"):
        statement = chunk.strip()
        if statement:
            yield statement


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _platform_name() -> str:
    try:
        return os.uname().sysname
    except AttributeError:  # Windows has no os.uname
        return ""


def default_db_path() -> str:
    """Platform-aware history location; ``SRT4U_HISTORY_DB`` overrides."""
    override = os.environ.get("SRT4U_HISTORY_DB")
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif _platform_name() == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "SRT4U", "history.db")


class HistoryStore:
    """Single-connection repository over the local history database."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or default_db_path()
        parent = os.path.dirname(os.path.abspath(self.path))
        try:
            os.makedirs(parent, exist_ok=True)
            if os.name != "nt":
                os.chmod(parent, 0o700)
        except OSError as exc:
            raise HistoryError(f"cannot prepare history directory: {exc}") from exc
        try:
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._migrate()
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot open history database: {exc}") from exc

    def _version(self) -> int:
        row = self._conn.execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row else 0

    def _migrate(self) -> None:
        """Apply pending migrations, one transaction per step.

        Deep-audit L11: this used to mix ``executescript`` (which implicitly
        commits before running) with a surrounding ``with self._conn`` block, so
        a failure midway could roll ``user_version`` back while leaving the DDL
        committed — DDL and version out of sync. Each step now runs inside its
        own explicit transaction and only advances ``user_version`` once that
        step is durable, so a failure always leaves a consistent state (either
        fully at N, or fully at N-1 and retried next open).
        """
        current = self._version()
        if current > SCHEMA_VERSION:
            raise HistoryError(
                f"history database is newer (v{current}) than supported "
                f"(v{SCHEMA_VERSION}); refusing to modify it"
            )
        for version in range(current + 1, SCHEMA_VERSION + 1):
            ddl = _MIGRATIONS[version]
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                for statement in _split_statements(ddl):
                    self._conn.execute(statement)
                self._conn.execute(f"PRAGMA user_version = {version}")
                self._conn.commit()
            except sqlite3.DatabaseError as exc:
                self._conn.rollback()
                raise HistoryError(
                    f"history migration to v{version} failed: {exc}"
                ) from exc

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.DatabaseError:
            pass

    def __enter__(self) -> "HistoryStore":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -- writes (single transaction each) -----------------------------------

    def record_run(self, operation: str, **fields: Any) -> int:
        """Insert one execution row; returns its id. All values parameterized."""
        try:
            with self._conn:
                return self._insert_run(operation, fields)
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot record run: {exc}") from exc

    def _insert_run(self, operation: str, fields: Dict[str, Any]) -> int:
        """Insert a run row inside the caller's transaction (no commit here)."""
        if not operation or not isinstance(operation, str):
            raise HistoryError("operation is required")
        values: Dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "operation": operation,
            "success": 1,
            "retry_count": 0,
            "fallback_used": 0,
            "qa_errors": 0,
            "qa_warnings": 0,
            "translation_failures": 0,
        }
        for key, value in fields.items():
            if key not in _RUN_COLUMNS:
                raise HistoryError(f"unknown run field: {key}")
            values[key] = value
        if isinstance(values.get("providers_used"), (list, tuple)):
            values["providers_used"] = json.dumps(
                list(values["providers_used"]), ensure_ascii=False, sort_keys=True
            )
        for flag in ("success", "fallback_used"):
            if values.get(flag) is not None:
                values[flag] = 1 if values[flag] else 0
        columns = [key for key in _RUN_COLUMNS if key in values]
        cursor = self._conn.execute(
            f"INSERT INTO runs ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [values[key] for key in columns],
        )
        return int(cursor.lastrowid)

    def record_qa_findings(
        self, run_id: int, findings: List[Any], limit: int = 500
    ) -> int:
        """Persist QA finding metadata (no subtitle texts). One transaction."""
        try:
            with self._conn:
                return self._insert_qa_findings(run_id, findings, limit)
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot record QA findings: {exc}") from exc

    def _insert_qa_findings(
        self, run_id: int, findings: List[Any], limit: int = 500
    ) -> int:
        """Insert findings inside the caller's transaction (no commit here)."""
        rows = []
        for finding in findings[:limit]:
            if isinstance(finding, dict):
                severity = finding.get("severity")
                rule = finding.get("rule")
                index = finding.get("subtitle_index")
                message = finding.get("message", "")
                metadata = finding.get("metadata")
            else:
                severity = getattr(finding, "severity", None)
                rule = getattr(finding, "rule", None)
                index = getattr(finding, "subtitle_index", None)
                message = getattr(finding, "message", "")
                metadata = getattr(finding, "metadata", None)
            if isinstance(metadata, (dict, list)):
                metadata = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            rows.append((run_id, severity, rule, index, str(message), metadata))
        if rows:
            self._conn.executemany(
                "INSERT INTO qa_findings "
                "(run_id, severity, rule, subtitle_index, message, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def record_processing_result(
        self,
        result: Any,
        *,
        operation: str,
        file_path: Optional[str] = None,
        file_format: Optional[str] = None,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        engine: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> int:
        """Build a run row from a ProcessingResult without importing services.

        Deep-audit L1: the run row and its QA findings are written in **one**
        transaction, so a failure while storing findings rolls the run back
        instead of leaving a half-recorded execution.

        Deep-audit L2: ``success`` means the same thing here as it does in
        ``record_pipeline_result`` — did this execution produce a usable
        result? It is resolved in this order: the explicit ``success``
        argument, then ``ProcessingResult.success`` (set by the pipeline-style
        outcome), then the translation metrics, and only then a successful run.
        A translation-free ``process`` run is no longer implicitly "successful"
        just because it had no metrics.
        """
        stats = getattr(result, "stats", None)
        metrics = getattr(result, "translation_metrics", None)
        qa_report = getattr(result, "qa_report", None)
        fields: Dict[str, Any] = {
            "file_path": file_path,
            "file_format": file_format,
            "source_language": source_language,
            "target_language": target_language,
            "provider": engine,
            "requested_provider": engine,
        }
        if metrics is not None:
            fields.update(
                provider=getattr(metrics, "provider", engine),
                requested_provider=getattr(metrics, "requested_provider", engine),
                model=getattr(metrics, "model", None),
                number_of_cues=getattr(metrics, "number_of_cues", None),
                characters_input=getattr(metrics, "characters_input", None),
                characters_output=getattr(metrics, "characters_output", None),
                words_input=getattr(metrics, "words_input", None),
                words_output=getattr(metrics, "words_output", None),
                duration_ms=getattr(metrics, "duration_ms", None),
                error_type=getattr(metrics, "error_type", None),
                retry_count=getattr(metrics, "retry_count", 0),
                fallback_used=getattr(metrics, "fallback_used", False),
                providers_used=getattr(metrics, "providers_used", None),
                input_tokens=getattr(metrics, "input_tokens", None),
                output_tokens=getattr(metrics, "output_tokens", None),
                total_tokens=getattr(metrics, "total_tokens", None),
                estimated_cost=getattr(metrics, "estimated_cost", None),
            )
        if success is None:
            success = getattr(result, "success", None)
        if success is None and metrics is not None:
            success = bool(getattr(metrics, "success", True))
        fields["success"] = True if success is None else bool(success)
        if stats is not None:
            fields["translation_failures"] = getattr(stats, "translation_failures", 0)
        findings: List[Any] = []
        if qa_report is not None:
            findings = list(getattr(qa_report, "findings", []) or [])
            fields["qa_errors"] = sum(
                1 for item in findings if _finding_attr(item, "severity") == "error"
            )
            fields["qa_warnings"] = sum(
                1 for item in findings if _finding_attr(item, "severity") == "warning"
            )
        try:
            with self._conn:
                run_id = self._insert_run(operation, fields)
                if qa_report is not None:
                    self._insert_qa_findings(run_id, findings)
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot record processing result: {exc}") from exc
        return run_id

    def record_transcription_result(
        self,
        result: Any,
        *,
        file_path: Optional[str] = None,
        file_format: Optional[str] = None,
    ) -> int:
        """Build a ``transcription`` run row from a TranscriptionResult.

        Only aggregates are stored: provider, model, detected language, cue
        count, media vs. processing durations, success, and error type. No
        transcript texts, audio, video, or secrets.
        """
        metrics = getattr(result, "metrics", None)
        segments = getattr(result, "segments", None) or []
        fields: Dict[str, Any] = {
            "file_path": file_path,
            "file_format": file_format,
            "source_language": getattr(result, "language", None)
            or getattr(metrics, "source_language", None),
            "provider": getattr(result, "provider", None) or "whisper",
            "requested_provider": getattr(result, "provider", None) or "whisper",
            "model": getattr(result, "model", None),
            "number_of_cues": len(segments),
            "media_duration_ms": getattr(result, "duration_ms", None),
            "duration_ms": getattr(result, "processing_time_ms", None),
            "success": bool(getattr(result, "success", True)),
            "error_type": getattr(result, "error_type", None),
        }
        return self.record_run("transcription", **fields)

    def record_benchmark_report(self, report: Any) -> List[int]:
        """Persist every BenchmarkRun in a single transaction; keep JSON/CSV."""
        runs = getattr(report, "runs", report) or []
        ids: List[int] = []
        try:
            with self._conn:
                for item in runs:
                    data = item.to_dict() if hasattr(item, "to_dict") else dict(item)
                    values = {
                        "timestamp": data.get("timestamp") or _utc_now_iso(),
                        "operation": "benchmark",
                        "source_language": data.get("source_language"),
                        "target_language": data.get("target_language"),
                        "provider": data.get("provider"),
                        "requested_provider": data.get("requested_provider"),
                        "model": data.get("model"),
                        "number_of_cues": data.get("number_of_cues"),
                        "characters_input": data.get("characters_input"),
                        "characters_output": data.get("characters_output"),
                        "words_input": data.get("words_input"),
                        "words_output": data.get("words_output"),
                        "duration_ms": data.get("duration_ms"),
                        "success": 1 if data.get("success") else 0,
                        "error_type": data.get("error_type"),
                        "retry_count": data.get("retry_count", 0) or 0,
                        "fallback_used": 1 if data.get("fallback_used") else 0,
                        "providers_used": _as_json_list(data.get("providers_used")),
                        "fallback_error_type": data.get("fallback_error_type"),
                        "input_tokens": data.get("input_tokens"),
                        "output_tokens": data.get("output_tokens"),
                        "total_tokens": data.get("total_tokens"),
                        "estimated_cost": data.get("estimated_cost"),
                        "benchmark_id": data.get("benchmark_id")
                        or getattr(report, "benchmark_id", None),
                        "run_index": data.get("run_index"),
                    }
                    columns = [key for key in _RUN_COLUMNS if key in values]
                    cursor = self._conn.execute(
                        f"INSERT INTO runs ({', '.join(columns)}) "
                        f"VALUES ({', '.join('?' for _ in columns)})",
                        [values[key] for key in columns],
                    )
                    ids.append(int(cursor.lastrowid))
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot record benchmark: {exc}") from exc
        return ids

    # -- reads -----------------------------------------------------------------

    def recent_runs(
        self,
        limit: int = 20,
        provider: Optional[str] = None,
        operation: Optional[str] = None,
        only_errors: bool = False,
        only_fallbacks: bool = False,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Newest-first rows; every filter is a bound parameter, never SQL text."""
        query = "SELECT * FROM runs WHERE 1 = 1"
        params: List[Any] = []
        if provider:
            query += " AND requested_provider = ?"
            params.append(provider)
        if operation:
            query += " AND operation = ?"
            params.append(operation)
        if only_errors:
            query += " AND success = 0"
        if only_fallbacks:
            query += " AND fallback_used = 1"
        if since:
            query += " AND timestamp >= ?"
            params.append(since)
        if until:
            query += " AND timestamp <= ?"
            params.append(until)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        try:
            rows = self._conn.execute(query, params).fetchall()
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot query history: {exc}") from exc
        return [_row_to_dict(row) for row in rows]

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE id = ?", (int(run_id),)
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot query history: {exc}") from exc
        return _row_to_dict(row) if row else None

    def get_findings(self, run_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self._conn.execute(
                "SELECT severity, rule, subtitle_index, message, metadata "
                "FROM qa_findings WHERE run_id = ? ORDER BY id",
                (int(run_id),),
            ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot query history: {exc}") from exc
        return [_row_to_dict(row) for row in rows]

    def run_stats(
        self, provider: Optional[str] = None, since: Optional[str] = None
    ) -> Dict[str, Any]:
        """Basic aggregates in SQL; distributions stay in the analysis layer."""
        query = (
            "SELECT COUNT(*), SUM(success), SUM(fallback_used), "
            "AVG(duration_ms), MIN(duration_ms), MAX(duration_ms) FROM runs WHERE 1 = 1"
        )
        params: List[Any] = []
        if provider:
            query += " AND requested_provider = ?"
            params.append(provider)
        if since:
            query += " AND timestamp >= ?"
            params.append(since)
        try:
            total, ok, fallbacks, avg_ms, min_ms, max_ms = self._conn.execute(
                query, params
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise HistoryError(f"cannot query history: {exc}") from exc
        return {
            "total": total or 0,
            "successful": ok or 0,
            "failed": (total or 0) - (ok or 0),
            "fallbacks": fallbacks or 0,
            "avg_duration_ms": avg_ms,
            "min_duration_ms": min_ms,
            "max_duration_ms": max_ms,
        }

    def export_rows(self, **filters: Any) -> List[Dict[str, Any]]:
        """Plain rows for offline ``pandas.DataFrame(rows)`` (no pandas here)."""
        return self.recent_runs(limit=100000, **filters)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    if isinstance(item.get("providers_used"), str):
        try:
            item["providers_used"] = json.loads(item["providers_used"])
        except (json.JSONDecodeError, TypeError):
            item["providers_used"] = []
    if isinstance(item.get("metadata"), str):
        try:
            item["metadata"] = json.loads(item["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass
    return item


def _as_json_list(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(list(value), ensure_ascii=False, sort_keys=True)


def _finding_attr(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _warn_history_unavailable(exc: Exception) -> None:
    """Log and swallow any history failure; history never breaks execution."""
    logger.warning("History unavailable (%s); execution continues", type(exc).__name__)


def record_safely(
    operation: str, db_path: Optional[str] = None, **fields: Any
) -> Optional[int]:
    """Best-effort recording; SQLite failure only logs, never raises."""
    try:
        with HistoryStore(db_path) as store:
            return store.record_run(operation, **fields)
    except Exception as exc:
        _warn_history_unavailable(exc)
    return None


def record_result_safely(
    result: Any, db_path: Optional[str] = None, **kwargs: Any
) -> Optional[int]:
    """Best-effort ProcessingResult recording; never raises."""
    try:
        with HistoryStore(db_path) as store:
            return store.record_processing_result(result, **kwargs)
    except Exception as exc:
        _warn_history_unavailable(exc)
    return None
