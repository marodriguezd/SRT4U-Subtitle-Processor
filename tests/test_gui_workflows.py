"""Offscreen MainWindow workflow tests.

Each test drives the real navigation and processing methods and checks the
resulting state and files. Worker completion is awaited with bounded waits;
translation providers are never reached because translation is switched off.
"""

import time

import pytest

from application.ui import main_window as main_window_module
from application.ui.main_window import MainWindow

WAIT = 15.0
SAMPLE_SRT = (
    "1\n00:00:01,000 --> 00:00:02,000\nHello there.\n\n"
    "2\n00:00:03,000 --> 00:00:04,000\nSecond line here.\n"
)
PAGE_COUNT = 10
RESULT_PAGE = 6


@pytest.fixture
def window(qapp):
    win = MainWindow()
    win.show()
    qapp.processEvents()
    yield win
    worker = getattr(win, "worker", None)
    if worker is not None and worker.isRunning():
        if hasattr(worker, "cancel"):
            worker.cancel()
        worker.wait(int(WAIT * 1000))
    win.close()
    qapp.processEvents()


@pytest.fixture
def warnings(monkeypatch):
    """Record warning dialogs instead of showing them."""
    shown = []
    monkeypatch.setattr(
        main_window_module.ThemedMessageBox,
        "warning",
        lambda *args, **kwargs: shown.append(args[1:]),
    )
    return shown


def _pump_until(qapp, predicate, timeout=WAIT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_navigation_switches_every_page_and_returns_home(window):
    for index in range(PAGE_COUNT):
        window._switch_page(index)
        assert window.stack.currentIndex() == index
    window._switch_page(0)
    assert window.stack.currentIndex() == 0


def test_clean_run_writes_processed_output_and_shows_result(window, qapp, tmp_path):
    source = tmp_path / "movie.srt"
    source.write_text(SAMPLE_SRT, encoding="utf-8")
    window._on_file_selected(str(source), "")
    window.toggle_translate.setChecked(False)
    window.toggle_clean.setChecked(True)

    window._start_processing()
    worker = window.worker
    assert worker is not None

    expected = tmp_path / "movie_processed.srt"
    assert _pump_until(qapp, lambda: window.stack.currentIndex() == RESULT_PAGE)
    assert worker.wait(int(WAIT * 1000))
    assert expected.exists()
    assert window.saved_output_path == str(expected)
    assert "Hello there." in expected.read_text(encoding="utf-8")
    assert window.last_result is not None


def test_start_without_a_file_warns_and_starts_no_worker(window, warnings):
    window._on_file_selected("", "")
    window._start_processing()

    assert len(warnings) == 1
    assert getattr(window, "worker", None) is None


def test_missing_file_is_rejected_without_crashing(window, warnings, tmp_path):
    window._on_file_selected(str(tmp_path / "gone.srt"), "")
    window._start_processing()

    assert len(warnings) == 1
    assert getattr(window, "worker", None) is None


def test_cancel_without_active_worker_is_a_no_op(window):
    window._cancel_worker()
    assert getattr(window, "worker", None) is None
