"""In-process background jobs for slow operations (translate/process).

Local-only: a bounded thread pool, no broker, no persistence. Cancellation is
best-effort — a queued job is dropped, a running job runs to completion and
its result is discarded.
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ..logging_setup import get_logger

logger = get_logger("api")

#: Retention defaults (deep-audit M9). Without these, ``_jobs`` grew without
#: bound and every finished job kept its full result payload alive for the
#: lifetime of the server.
DEFAULT_MAX_JOBS = 200
DEFAULT_TTL_SECONDS = 3600.0

#: States from which a job can never be evicted: it is still doing work, or the
#: caller has not been told yet.
_LIVE_STATES = {"queued", "running"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobError(Exception):
    """Expected job failure carrying a client-safe message."""


class JobManager:
    """Submit callables, poll by id. Thread-safe via a single lock."""

    def __init__(
        self,
        max_workers: int = 2,
        *,
        max_jobs: int = DEFAULT_MAX_JOBS,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ):
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="srt4u-api-job"
        )
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._max_jobs = max(1, max_jobs)
        self._ttl_seconds = max(0.0, float(ttl_seconds))

    def submit(
        self,
        operation: str,
        func: Callable[[], Any],
        on_drop: Optional[Callable[[], None]] = None,
    ) -> str:
        """Enqueue ``func``. ``on_drop`` releases resources (e.g. temp files)
        when a still-queued job is cancelled before it ever runs."""
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "operation": operation,
                "status": "queued",
                "created_at": _utc_now_iso(),
                "finished_at": None,
                "error": None,
                "result": None,
                "cancel_requested": False,
            }
        self._executor.submit(self._run, job_id, func, on_drop)
        return job_id

    def _run(
        self,
        job_id: str,
        func: Callable[[], Any],
        on_drop: Optional[Callable[[], None]],
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["cancel_requested"]:
                if job is not None:
                    job["status"] = "cancelled"
                    job["finished_at"] = _utc_now_iso()
                    self._prune_locked()
                drop = on_drop
                on_drop = None
            else:
                drop = None
                job["status"] = "running"
        if drop is not None:
            try:
                drop()
            except Exception as exc:
                logger.error("Job drop cleanup failed (%s)", type(exc).__name__)
            return
        try:
            result = func()
        except JobError as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["status"] = "cancelled" if job["cancel_requested"] else "failed"
                    job["error"] = str(exc) or "error en el job"
                    job["finished_at"] = _utc_now_iso()
                    self._prune_locked()
            return
        except Exception as exc:  # job boundary: sanitize, never leak traces
            logger.error("Job failed (%s)", type(exc).__name__)
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    if job["cancel_requested"]:
                        job["status"] = "cancelled"
                    else:
                        job["status"] = "failed"
                        job["error"] = "error interno del job"
                    job["finished_at"] = _utc_now_iso()
                    self._prune_locked()
            return
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job["cancel_requested"]:
                    job["status"] = "cancelled"
                else:
                    job["status"] = "completed"
                    job["result"] = result
                job["finished_at"] = _utc_now_iso()
                self._prune_locked()

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _prune_locked(self) -> None:
        """Drop finished jobs that are too old or beyond the retention cap.

        Only terminal jobs are ever evicted, and the oldest go first, so a
        client that polls normally always finds its own job. Callers must hold
        ``self._lock``.

        The cap compares the *total* dict size (live + finished minus already
        dropped) against ``max_jobs``: dropping the oldest finished rows while
        the total still exceeds the cap. The previous condition compared
        ``survivors + len(to_drop) >= max_jobs`` (survivors = live jobs), which
        only pruned while live jobs alone filled the cap — under fast workers
        the final prune of a burst saw few live jobs and stranded finished
        rows above the cap (race flake in
        ``test_job_manager_prunes_completed_jobs``).
        """
        if not self._jobs:
            return
        finished = sorted(
            (job for job in self._jobs.values() if job["status"] not in _LIVE_STATES),
            key=lambda job: (job["finished_at"] or job["created_at"], job["job_id"]),
        )
        to_drop: List[str] = []
        for job in finished:
            over_cap = len(self._jobs) - len(to_drop) > self._max_jobs
            age = self._age_seconds(job)
            expired = (
                self._ttl_seconds > 0 and age is not None and age > self._ttl_seconds
            )
            if over_cap or expired:
                to_drop.append(job["job_id"])
        for job_id in to_drop:
            self._jobs.pop(job_id, None)
        if to_drop:
            logger.debug("Jobs retencionados: %s eliminados", len(to_drop))

    @staticmethod
    def _age_seconds(job: Dict[str, Any]) -> Optional[float]:
        stamp = job.get("finished_at") or job.get("created_at")
        if not stamp:
            return None
        try:
            moment = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - moment).total_seconds()

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = sorted(
                self._jobs.values(), key=lambda item: item["created_at"], reverse=True
            )
            return [dict(job) for job in jobs[: max(1, limit)]]

    def cancel(self, job_id: str) -> Optional[str]:
        """Returns the resulting status, or None for unknown jobs."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job["status"] not in {"queued", "running"}:
                return job["status"]
            job["cancel_requested"] = True
            if job["status"] == "queued":
                job["status"] = "cancelled"
                job["finished_at"] = _utc_now_iso()
                self._prune_locked()
            return job["status"]

    def wait_for(
        self, job_id: str, timeout: float = 30.0, interval: float = 0.05
    ) -> Optional[Dict[str, Any]]:
        """Poll until terminal state; test/ops helper, not an endpoint."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.get(job_id)
            if job is None:
                return None
            if job["status"] in {"completed", "failed", "cancelled"}:
                return job
            time.sleep(interval)
        return self.get(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
