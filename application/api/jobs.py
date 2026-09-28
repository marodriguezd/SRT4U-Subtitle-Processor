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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobError(Exception):
    """Expected job failure carrying a client-safe message."""


class JobManager:
    """Submit callables, poll by id. Thread-safe via a single lock."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="srt4u-api-job"
        )
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

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
                drop = on_drop
                on_drop = None
            else:
                drop = None
                job["status"] = "running"
        if drop is not None:
            try:
                drop()
            except Exception:
                logger.exception("Job %s drop cleanup failed", job_id)
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
            return
        except Exception:  # job boundary: sanitize, never leak traces
            logger.exception("Job %s failed", job_id)
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    if job["cancel_requested"]:
                        job["status"] = "cancelled"
                    else:
                        job["status"] = "failed"
                        job["error"] = "error interno del job"
                    job["finished_at"] = _utc_now_iso()
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

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

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
