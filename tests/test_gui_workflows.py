"""Offscreen MainWindow workflow tests.

Each test drives the real navigation and processing methods and checks the
resulting state and files. Worker completion is awaited with bounded waits;
translation providers are never reached over the network: translation is
either switched off or routed to a local fake provider registered only for
the duration of one test.
"""

import threading
import time
from pathlib import Path

import pytest

from application.services.history_store import HistoryStore
from application.services.subtitle_service import SubtitleCancelledError, SubtitleItem
from application.services.translation_providers import (
    ProviderAuthenticationError,
    ProviderRegistry,
    TranslationProvider,
)
from application.services.video_burner_service import BurnInOptions
from application.ui import main_window as main_window_module
from application.ui.burn_in_dialog import BurnInDialog
from application.ui.main_window import MainWindow

WAIT = 15.0
SAMPLE_SRT = (
    "1\n00:00:01,000 --> 00:00:02,000\nHello there.\n\n"
    "2\n00:00:03,000 --> 00:00:04,000\nSecond line here.\n"
)
PAGE_COUNT = 10
RESULT_PAGE = 6
FAKE_ENGINE = "guitestfake"


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


@pytest.fixture
def criticals(monkeypatch):
    shown = []
    monkeypatch.setattr(
        main_window_module.ThemedMessageBox,
        "critical",
        lambda *args, **kwargs: shown.append(args[1:]),
    )
    return shown


@pytest.fixture
def infos(monkeypatch):
    shown = []
    monkeypatch.setattr(
        main_window_module.ThemedMessageBox,
        "information",
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


def _wait_for_batch(window, qapp):
    """Wait for the batch worker: pump queued signals, then join the thread."""
    worker = getattr(window, "batch_worker", None)
    assert worker is not None, "batch worker was not started"
    assert _pump_until(qapp, lambda: not window._batch_running), "batch timed out"
    assert worker.wait(int(WAIT * 1000))
    qapp.processEvents()


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


def test_batch_processes_every_file_and_marks_each_completed(
    window, qapp, tmp_path, monkeypatch, infos
):
    sources = []
    for name in ("first.srt", "second.srt", "third.srt"):
        path = tmp_path / name
        path.write_text(SAMPLE_SRT, encoding="utf-8")
        sources.append(str(path))
    monkeypatch.setattr(
        main_window_module, "ask_open_files", lambda *args, **kwargs: sources
    )
    window.toggle_translate.setChecked(False)
    window.toggle_clean.setChecked(True)

    window._add_batch_files()
    assert window.batch_table.rowCount() == len(sources)

    window._run_batch_processing()
    _wait_for_batch(window, qapp)

    completed = main_window_module.t("batch.status_completed")
    for row, source in enumerate(sources):
        processed = tmp_path / f"{Path(source).stem}_processed.srt"
        assert processed.exists()
        assert window.batch_table.item(row, 3).text() == completed
    assert len(infos) == 1


def test_batch_worker_stops_after_a_cooperative_cancel(
    window, qapp, tmp_path, monkeypatch, infos
):
    """A-4: cancelling mid-batch stops before the next file is started."""
    sources = []
    for name in ("a.srt", "b.srt", "c.srt"):
        path = tmp_path / name
        path.write_text(SAMPLE_SRT, encoding="utf-8")
        sources.append(str(path))
    monkeypatch.setattr(
        main_window_module, "ask_open_files", lambda *args, **kwargs: sources
    )
    window.toggle_translate.setChecked(False)
    window._add_batch_files()

    original = window.subtitle_service.process_subtitles
    started = []

    def _process_and_cancel(*args, **kwargs):
        started.append(kwargs.get("file_path"))
        result = original(*args, **kwargs)
        window.cancel_batch()
        return result

    monkeypatch.setattr(
        window.subtitle_service, "process_subtitles", _process_and_cancel
    )

    window._run_batch_processing()
    _wait_for_batch(window, qapp)

    assert started == [sources[0]]
    assert window.batch_table.item(0, 3).text() == main_window_module.t(
        "batch.status_completed"
    )
    # A cancelled batch is not reported as a completed one.
    assert infos == []


def test_batch_with_no_rows_informs_and_does_nothing(window, infos):
    window._clear_batch_table()
    window._run_batch_processing()

    assert len(infos) == 1
    assert window.batch_table.rowCount() == 0


def test_changing_the_language_updates_both_selectors_and_i18n(window):
    original = window.i18n.current_language
    target = "de" if original != "de" else "it"
    index = window.cb_top_lang.findData(target)
    assert index >= 0

    window.cb_top_lang.setCurrentIndex(index)

    assert window.i18n.current_language == target
    assert window.cb_settings_lang.currentData() == target

    settings_index = window.cb_settings_lang.findData(original)
    window.cb_settings_lang.setCurrentIndex(settings_index)
    assert window.i18n.current_language == original
    assert window.cb_top_lang.currentData() == original


def test_history_page_lists_recorded_runs_and_filters_by_operation(
    window, qapp, tmp_path, monkeypatch, infos
):
    source = tmp_path / "history.srt"
    source.write_text(SAMPLE_SRT, encoding="utf-8")
    monkeypatch.setattr(
        main_window_module, "ask_open_files", lambda *args, **kwargs: [str(source)]
    )
    window.toggle_translate.setChecked(False)
    window._add_batch_files()
    window._run_batch_processing()
    _wait_for_batch(window, qapp)

    window._refresh_history()
    assert window.history_table.rowCount() >= 1
    assert window.history_table.item(0, 1).text() == "history.srt"

    with HistoryStore() as store:
        processed = store.recent_runs(operation="process")
        analyzed = store.recent_runs(operation="analyze")
    assert len(processed) >= 1
    assert analyzed == []


def _burn_dialog(qapp, video_path, subtitle_items):
    dialog = BurnInDialog(video_path=video_path, subtitle_items=subtitle_items)
    dialog.show()
    qapp.processEvents()
    return dialog


def test_burn_in_rejects_missing_video_without_emitting(qapp, warnings, tmp_path):
    items = [SubtitleItem(1, 0, 1000, "Hi")]
    dialog = _burn_dialog(qapp, str(tmp_path / "absent.mp4"), items)
    emitted = []
    dialog.burn_requested.connect(lambda *args: emitted.append(args))
    try:
        dialog._on_start_clicked()
    finally:
        dialog.close()

    assert len(warnings) == 1
    assert emitted == []


def test_burn_in_rejects_output_equal_to_input(qapp, warnings, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not a real video")
    items = [SubtitleItem(1, 0, 1000, "Hi")]
    dialog = _burn_dialog(qapp, str(video), items)
    emitted = []
    dialog.burn_requested.connect(lambda *args: emitted.append(args))
    try:
        dialog.txt_output.setText(str(video))
        dialog._on_start_clicked()
    finally:
        dialog.close()

    assert len(warnings) == 1
    assert emitted == []


def test_burn_in_rejects_missing_subtitles(qapp, warnings, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not a real video")
    dialog = _burn_dialog(qapp, str(video), [])
    emitted = []
    dialog.burn_requested.connect(lambda *args: emitted.append(args))
    try:
        dialog.txt_output.setText(str(tmp_path / "out.mp4"))
        dialog._on_start_clicked()
    finally:
        dialog.close()

    assert len(warnings) == 1
    assert emitted == []


def test_burn_in_valid_request_emits_selected_options(qapp, warnings, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not a real video")
    items = [SubtitleItem(1, 0, 1000, "Hi")]
    dialog = _burn_dialog(qapp, str(video), items)
    emitted = []
    dialog.burn_requested.connect(lambda *args: emitted.append(args))
    try:
        output = str(tmp_path / "out.mp4")
        dialog.txt_output.setText(output)
        dialog._on_start_clicked()
    finally:
        dialog.close()

    assert warnings == []
    assert len(emitted) == 1
    v_path, o_path, subs, opts = emitted[0]
    assert v_path == str(video)
    assert o_path == output
    assert subs == items
    assert isinstance(opts, BurnInOptions)
    assert opts.fix_overlaps is True


class _AuthFailingProvider(TranslationProvider):
    """Local provider that always rejects credentials, without any network call."""

    name = FAKE_ENGINE

    def translate(self, text, source_language, target_language, *, context=None):
        raise ProviderAuthenticationError("rejected by the test double")


def test_translation_failure_keeps_original_text_and_warns(
    window, qapp, tmp_path, monkeypatch, warnings
):
    monkeypatch.setitem(
        ProviderRegistry._factories,
        FAKE_ENGINE,
        lambda config_service=None: _AuthFailingProvider(),
    )
    source = tmp_path / "failing.srt"
    source.write_text(SAMPLE_SRT, encoding="utf-8")
    window._on_file_selected(str(source), "")
    window.cb_engine.addItem("Test double", FAKE_ENGINE)
    window.cb_engine.setCurrentIndex(window.cb_engine.count() - 1)
    window.toggle_translate.setChecked(True)
    window.toggle_clean.setChecked(False)
    window.toggle_parallel.setChecked(False)

    window._start_processing()
    worker = window.worker
    assert worker is not None
    assert _pump_until(qapp, lambda: window.stack.currentIndex() == RESULT_PAGE)
    assert worker.wait(int(WAIT * 1000))
    qapp.processEvents()

    # The service keeps the original cue text when a provider fails, so the
    # output is still written; the user is warned about the incomplete result.
    expected = tmp_path / "failing_processed.srt"
    assert expected.exists()
    assert "Hello there." in expected.read_text(encoding="utf-8")
    assert window.saved_output_path == str(expected)
    assert len(warnings) == 1
    assert not window.modal.isVisible()


def test_cancelling_active_processing_writes_nothing(
    window, qapp, tmp_path, monkeypatch
):
    started = threading.Event()

    def blocking_process(**kwargs):
        started.set()
        kwargs["cancel_event"].wait(WAIT)
        raise SubtitleCancelledError("cancelled by the test")

    source = tmp_path / "slow.srt"
    source.write_text(SAMPLE_SRT, encoding="utf-8")
    window._on_file_selected(str(source), "")
    window.toggle_translate.setChecked(False)
    window.toggle_clean.setChecked(True)
    monkeypatch.setattr(window.subtitle_service, "process_subtitles", blocking_process)

    window._start_processing()
    worker = window.worker
    assert _pump_until(qapp, started.is_set)

    window._cancel_worker()
    assert worker.wait(int(WAIT * 1000))
    assert _pump_until(qapp, lambda: not window.modal.isVisible())

    assert not (tmp_path / "slow_processed.srt").exists()
    assert not window.saved_output_path
    assert window.stack.currentIndex() != RESULT_PAGE
