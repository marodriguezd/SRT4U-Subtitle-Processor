"""Deterministic workflow tests for the desktop ProcessWorker.

``ProcessWorker.run()`` is invoked directly on the test thread. Signals are
connected to plain Python callables, so emissions are synchronous and no event
loop or sleep is needed.
"""

import threading

import pytest

from application.services.subtitle_service import SubtitleCancelledError
from application.ui.main_window import ProcessWorker


class _FakeService:
    """Stands in for SubtitleService and records the call arguments."""

    def __init__(self, result=None, error=None, on_call=None):
        self.result = result
        self.error = error
        self.on_call = on_call
        self.calls = []

    def process_subtitles(self, **kwargs):
        self.calls.append(kwargs)
        if self.on_call is not None:
            self.on_call(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _worker(service, **overrides):
    params = dict(
        file_path="/tmp/synthetic.srt",
        do_clean=True,
        do_translate=False,
        target_lang="es",
        source_lang="en",
        engine="google",
    )
    params.update(overrides)
    worker = ProcessWorker(service=service, **params)
    signals = {"completed": [], "failed": [], "cancelled": [], "steps": []}
    worker.completed.connect(lambda payload: signals["completed"].append(payload))
    worker.failed.connect(lambda message: signals["failed"].append(message))
    worker.cancelled.connect(lambda: signals["cancelled"].append(True))
    worker.step_updated.connect(
        lambda name, payload: signals["steps"].append((name, payload))
    )
    return worker, signals


def test_success_emits_completed_with_service_result(qapp):
    sentinel = object()
    service = _FakeService(result=sentinel)
    worker, signals = _worker(service)

    worker.run()

    assert signals["completed"] == [sentinel]
    assert signals["failed"] == []
    assert signals["cancelled"] == []
    call = service.calls[0]
    assert call["file_path"] == "/tmp/synthetic.srt"
    assert call["do_clean"] is True
    assert call["target_language"] == "es"
    assert call["source_language"] == "en"
    assert call["engine"] == "google"
    assert call["cancel_event"] is worker.cancel_event


def test_progress_callback_is_forwarded_as_step_signal(qapp):
    def emit_progress(kwargs):
        kwargs["progress_callback"]("cleaning", {"done": 1})

    service = _FakeService(result=object(), on_call=emit_progress)
    worker, signals = _worker(service)

    worker.run()

    assert signals["steps"] == [("cleaning", {"done": 1})]


def test_service_error_emits_sanitized_failure_only(qapp, caplog):
    secret = "api_key=SUPER-SECRET-123 /home/alice/private.srt"
    service = _FakeService(error=RuntimeError(secret))
    worker, signals = _worker(service)

    worker.run()

    assert signals["completed"] == []
    assert signals["cancelled"] == []
    assert len(signals["failed"]) == 1
    message = signals["failed"][0]
    assert secret not in message
    assert "SUPER-SECRET" not in message
    assert "/home/alice" not in message


def test_cancellation_exception_emits_cancelled_not_failed(qapp):
    service = _FakeService(error=SubtitleCancelledError("stopped"))
    worker, signals = _worker(service)

    worker.run()

    assert signals["cancelled"] == [True]
    assert signals["failed"] == []
    assert signals["completed"] == []


def test_cancel_requested_during_run_suppresses_completed(qapp):
    def request_cancel(_kwargs):
        worker.cancel()

    service = _FakeService(result=object(), on_call=request_cancel)
    worker, signals = _worker(service)

    worker.run()

    assert signals["cancelled"] == [True]
    assert signals["completed"] == []
    assert worker.cancel_event.is_set()


def test_cancel_event_is_shared_and_thread_safe_flag(qapp):
    service = _FakeService(result=object())
    worker, _ = _worker(service)

    assert isinstance(worker.cancel_event, threading.Event)
    assert not worker.cancel_event.is_set()
    worker.cancel()
    assert worker.cancel_event.is_set()


@pytest.mark.parametrize("parallel", [True, False])
def test_parallel_flag_is_passed_through(qapp, parallel):
    service = _FakeService(result=object())
    worker, _ = _worker(service, parallel=parallel)

    worker.run()

    assert service.calls[0]["parallel"] is parallel
