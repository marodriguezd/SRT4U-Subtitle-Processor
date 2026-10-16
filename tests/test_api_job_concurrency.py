"""Deterministic lifecycle tests for the in-process job manager.

Blocking uses events and bounded waits; TTL uses an injected clock, so no test
depends on the speed of the machine it runs on.
"""

import threading
from datetime import datetime, timezone

import pytest

import application.api.jobs as jobs_module
from application.api.jobs import JobManager, JobQueueFullError

WAIT = 5.0
BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Gate:
    """Callable job body that holds a worker until the test releases it."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self):
        self.started.set()
        self.release.wait(WAIT)
        return "gated"


class _Clock(datetime):
    """Datetime subclass whose ``now`` returns a value the test controls."""

    current = BASE_TIME

    @classmethod
    def now(cls, tz=None):
        return cls.current


@pytest.fixture
def make_manager():
    managers = []

    def factory(**kwargs):
        manager = JobManager(**kwargs)
        managers.append(manager)
        return manager

    yield factory
    for manager in managers:
        manager.shutdown()


@pytest.fixture
def make_gate():
    gates = []

    def factory():
        gate = _Gate()
        gates.append(gate)
        return gate

    yield factory
    for gate in gates:
        gate.release.set()


def test_concurrent_submissions_fill_queue_exactly_to_capacity(make_manager, make_gate):
    manager = make_manager(max_workers=1, max_queued_jobs=3)
    gate = make_gate()
    manager.submit("blocker", gate)
    assert gate.started.wait(WAIT)

    attempts = 20
    barrier = threading.Barrier(attempts)
    lock = threading.Lock()
    accepted_ids = []
    rejected = []
    drops = []
    errors = []

    def submit(index):
        try:
            barrier.wait(WAIT)
            job_id = manager.submit(
                "job", lambda: "ok", on_drop=lambda: drops.append(index)
            )
            with lock:
                accepted_ids.append(job_id)
        except JobQueueFullError:
            with lock:
                rejected.append(index)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT)
        assert not thread.is_alive()

    assert errors == []
    assert len(accepted_ids) == 3
    assert len(rejected) == attempts - 3
    # Each rejected submission releases its resources exactly once and no
    # accepted submission is ever dropped while it is still pending.
    assert sorted(drops) == sorted(rejected)

    gate.release.set()
    for job_id in accepted_ids:
        assert manager.wait_for(job_id)["status"] == "completed"
    assert sorted(drops) == sorted(rejected)


def test_retention_cap_keeps_most_recent_finished_jobs(make_manager):
    manager = make_manager(max_workers=1, max_jobs=2, ttl_seconds=0)
    job_ids = []
    for i in range(5):
        # Wait per job: the cap may evict earlier finished jobs as later ones land.
        job_id = manager.submit("op", lambda i=i: i)
        assert manager.wait_for(job_id)["status"] == "completed"
        job_ids.append(job_id)

    manager.prune()
    retained = {job["job_id"] for job in manager.list(limit=100)}
    assert len(retained) == 2
    assert job_ids[-1] in retained


def test_live_jobs_are_never_evicted_even_above_cap(make_manager, make_gate):
    manager = make_manager(max_workers=2, max_jobs=1, max_queued_jobs=10)
    first, second = make_gate(), make_gate()
    running_a = manager.submit("a", first)
    running_b = manager.submit("b", second)
    assert first.started.wait(WAIT)
    assert second.started.wait(WAIT)

    # Both workers are busy, so this job stays queued; cancelling it makes a
    # terminal row that the cap may evict, but the two running jobs may not be.
    queued = manager.submit("c", lambda: "never")
    assert manager.cancel(queued) == "cancelled"

    assert manager.get(queued) is None
    assert manager.get(running_a)["status"] == "running"
    assert manager.get(running_b)["status"] == "running"


def test_ttl_evicts_only_finished_jobs_past_their_age(make_manager, monkeypatch):
    monkeypatch.setattr(jobs_module, "datetime", _Clock)
    _Clock.current = BASE_TIME
    manager = make_manager(max_workers=1, max_jobs=100, ttl_seconds=60)

    old = manager.submit("op", lambda: "old")
    assert manager.wait_for(old)["status"] == "completed"

    _Clock.current = BASE_TIME.replace(second=30)
    manager.prune()
    assert manager.get(old) is not None

    _Clock.current = BASE_TIME.replace(minute=1, second=1)
    manager.prune()
    assert manager.get(old) is None


def test_ttl_never_evicts_a_running_job(make_manager, make_gate, monkeypatch):
    monkeypatch.setattr(jobs_module, "datetime", _Clock)
    _Clock.current = BASE_TIME
    manager = make_manager(max_workers=1, max_jobs=100, ttl_seconds=60)
    gate = make_gate()
    running = manager.submit("op", gate)
    assert gate.started.wait(WAIT)

    _Clock.current = BASE_TIME.replace(hour=5)
    manager.prune()
    assert manager.get(running)["status"] == "running"


def test_cancelled_queued_job_never_runs_and_drops_once(make_manager, make_gate):
    manager = make_manager(max_workers=1, max_queued_jobs=5)
    gate = make_gate()
    manager.submit("blocker", gate)
    assert gate.started.wait(WAIT)

    ran = []
    drops = []
    queued = manager.submit(
        "op", lambda: ran.append(1), on_drop=lambda: drops.append(1)
    )
    assert manager.cancel(queued) == "cancelled"
    assert manager.cancel(queued) == "cancelled"

    gate.release.set()
    # One worker runs jobs FIFO, so once this sentinel completes the cancelled
    # job's worker turn has already been consumed.
    sentinel = manager.submit("sentinel", lambda: "done")
    assert manager.wait_for(sentinel)["status"] == "completed"

    assert ran == []
    assert drops == [1]
    assert manager.get(queued)["status"] == "cancelled"


def test_running_job_cancellation_discards_its_result(make_manager, make_gate):
    manager = make_manager(max_workers=1)
    gate = make_gate()
    job_id = manager.submit("op", gate)
    assert gate.started.wait(WAIT)

    assert manager.cancel(job_id) == "running"
    gate.release.set()

    job = manager.wait_for(job_id)
    assert job["status"] == "cancelled"
    assert job["result"] is None
    assert job["error"] is None


def test_shutdown_cancels_queued_jobs_once_and_lets_running_finish(
    make_manager, make_gate
):
    manager = make_manager(max_workers=1, max_queued_jobs=5)
    gate = make_gate()
    running = manager.submit("blocker", gate)
    assert gate.started.wait(WAIT)

    ran = []
    drops = []
    queued = manager.submit(
        "op", lambda: ran.append(1), on_drop=lambda: drops.append(1)
    )

    manager.shutdown()
    assert manager.get(queued)["status"] == "cancelled"
    assert drops == [1]

    gate.release.set()
    assert manager.wait_for(running)["status"] == "completed"
    assert ran == []
    assert drops == [1]


def test_executor_submit_failure_releases_resources_once(make_manager, monkeypatch):
    manager = make_manager()

    def broken_submit(*args, **kwargs):
        raise RuntimeError("pool unavailable")

    monkeypatch.setattr(manager._executor, "submit", broken_submit)
    drops = []
    with pytest.raises(RuntimeError, match="pool unavailable"):
        manager.submit("op", lambda: 1, on_drop=lambda: drops.append(1))

    assert drops == [1]
    assert manager.list() == []


def test_submit_after_shutdown_is_rejected_and_drops_once(make_manager):
    manager = make_manager()
    manager.shutdown()

    drops = []
    with pytest.raises(RuntimeError, match="shut down"):
        manager.submit("op", lambda: 1, on_drop=lambda: drops.append(1))

    assert drops == [1]
    assert manager.list() == []
