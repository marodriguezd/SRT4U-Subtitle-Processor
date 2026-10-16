"""Deterministic lifecycle tests for the in-process API ``JobManager``.

Interleavings are forced with explicit events and direct calls instead of
sleeps, so each test exercises one ordering on every run.
"""

import threading

import pytest

from application.api.jobs import JobManager, JobQueueFullError


@pytest.fixture
def manager():
    created = []

    def _make(**kwargs):
        mgr = JobManager(**kwargs)
        created.append(mgr)
        return mgr

    yield _make
    for mgr in created:
        mgr.shutdown()


def test_shutdown_drops_queued_job_and_worker_never_runs_it(monkeypatch, manager):
    """A job cancelled by shutdown must not run even if its worker reaches it later.

    The executor's own cancellation is bypassed on purpose: the worker picks up
    the callable after shutdown already consumed the drop callback, which is the
    window that previously flipped the job back to ``running``.
    """
    mgr = manager(max_workers=1)
    scheduled = []
    monkeypatch.setattr(
        mgr._executor, "submit", lambda fn, *args: scheduled.append((fn, args))
    )
    ran = []
    drops = []
    job_id = mgr.submit(
        "translate", lambda: ran.append(1), on_drop=lambda: drops.append(1)
    )

    mgr.shutdown()
    fn, args = scheduled[0]
    fn(*args)

    assert ran == []
    assert drops == [1]
    assert mgr.get(job_id)["status"] == "cancelled"


def test_queue_full_rejection_runs_drop_exactly_once(manager):
    mgr = manager(max_workers=1, max_queued_jobs=1)
    release = threading.Event()
    started = threading.Event()

    def _blocker():
        started.set()
        release.wait(timeout=10)
        return "done"

    try:
        running_id = mgr.submit("process", _blocker)
        assert started.wait(timeout=10)
        queued_id = mgr.submit("process", lambda: "queued")

        drops = []
        with pytest.raises(JobQueueFullError):
            mgr.submit("process", lambda: "rejected", on_drop=lambda: drops.append(1))

        assert drops == [1]
        assert mgr.get(queued_id)["status"] == "queued"
        assert mgr.get(running_id)["status"] == "running"
    finally:
        release.set()


def test_cancel_while_queued_drops_once_and_never_runs(manager):
    mgr = manager(max_workers=1)
    release = threading.Event()
    started = threading.Event()

    def _blocker():
        started.set()
        release.wait(timeout=10)
        return "done"

    try:
        mgr.submit("process", _blocker)
        assert started.wait(timeout=10)
        ran = []
        drops = []
        queued_id = mgr.submit(
            "translate", lambda: ran.append(1), on_drop=lambda: drops.append(1)
        )

        assert mgr.cancel(queued_id) == "cancelled"
        assert mgr.cancel(queued_id) == "cancelled"
    finally:
        release.set()

    final = mgr.wait_for(queued_id, timeout=10)
    assert final is not None and final["status"] == "cancelled"
    assert ran == []
    assert drops == [1]
