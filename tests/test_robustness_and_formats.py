"""Regression and robustness unit tests covering formats, edge cases, and workers.

Tests cover:
- All subtitle formats (.srt, .vtt, .ass, .ssa, .txt) round-tripping
- Multi-hour files (>99h) across formats
- Malformed timestamps and empty cue detection (ParseIssue tracking)
- Batch processing error isolation and cooperative cancellation
- Worker thread cancellation and state isolation
- Atomic write protection and cleanup determinism
"""

import os
import threading
import time

import pytest

from application.services.subtitle_service import (
    SubtitleService,
    SubtitleCancelledError,
    parse_timestamp_to_ms,
    ms_to_srt_time,
    ms_to_vtt_time,
    ms_to_ass_time,
)
from application.services.atomic_write import atomic_write_text
from application.ui.main_window import MainWindow, ProcessWorker
from PyQt6.QtWidgets import QTableWidgetItem


@pytest.fixture
def service():
    return SubtitleService()


def test_ssa_format_parsing_and_formatting(service):
    """Verify .ssa format parsing with 'Marked=0' and format roundtrip."""
    ssa_content = """[Script Info]
Title: Sample SSA
ScriptType: v4.00

[V4 Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, TertiaryColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, AlphaLevel, Encoding
Style: Default,Arial,20,16777215,65535,0,0,0,0,1,2,2,2,20,20,20,0,0

[Events]
Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: Marked=0,0:01:00.00,0:01:05.00,Default,NTP,0000,0000,0000,!Effect,First SSA line\\NSecond line
Dialogue: 0,0:02:00.00,0:02:04.50,Default,,0,0,0,,Second cue in SSA
"""
    items = service.parse_subtitles(ssa_content, "ssa")
    assert len(items) == 2
    assert items[0].index == 1
    assert items[0].start_ms == 60000
    assert items[0].end_ms == 65000
    assert "First SSA line\nSecond line" in items[0].text

    assert items[1].index == 2
    assert items[1].start_ms == 120000
    assert items[1].end_ms == 124500
    assert items[1].text == "Second cue in SSA"

    rendered_ssa = service.format_output(items, "ssa")
    assert "[Events]" in rendered_ssa
    assert "Dialogue:" in rendered_ssa
    reparsed = service.parse_subtitles(rendered_ssa, "ssa")
    assert len(reparsed) == 2
    assert reparsed[0].text == items[0].text


def test_txt_format_roundtrip_with_crlf(service):
    """Verify plain text format with CRLF and LF newlines."""
    txt_content = (
        "Line 1 of subtitles\r\nLine 2 of subtitles\r\n\r\nLine 3 after blank\n"
    )
    items = service.parse_subtitles(txt_content, "txt")
    assert len(items) == 3
    assert items[0].text == "Line 1 of subtitles"
    assert items[1].text == "Line 2 of subtitles"
    assert items[2].text == "Line 3 after blank"
    assert items[1].start_ms > items[0].start_ms

    out_txt = service.format_output(items, "txt")
    assert "Line 1 of subtitles" in out_txt
    assert "Line 2 of subtitles" in out_txt


def test_multi_hour_timestamps_across_formats(service):
    """Verify timestamps > 99 hours round-trip cleanly in SRT, VTT, and ASS."""
    ms = (125 * 3600 + 30 * 60 + 15) * 1000 + 500

    srt_time = ms_to_srt_time(ms)
    assert srt_time == "125:30:15,500"
    assert parse_timestamp_to_ms(srt_time) == ms

    vtt_time = ms_to_vtt_time(ms)
    assert vtt_time == "125:30:15.500"
    assert parse_timestamp_to_ms(vtt_time) == ms

    ass_time = ms_to_ass_time(ms)
    assert ass_time == "125:30:15.50"

    srt_content = "1\n125:30:15,500 --> 125:30:20,000\nExtreme duration cue\n"
    items = service.parse_subtitles(srt_content, "srt")
    assert len(items) == 1
    assert items[0].start_ms == ms
    assert items[0].end_ms == ms + 4500
    assert service.format_output(items, "srt").strip() == srt_content.strip()

    vtt_content = "WEBVTT\n\n1\n125:30:15.500 --> 125:30:20.000\nExtreme VTT cue\n"
    vtt_items = service.parse_subtitles(vtt_content, "vtt")
    assert len(vtt_items) == 1
    assert vtt_items[0].start_ms == ms


def test_malformed_timestamp_minutes_seconds_out_of_range(service):
    """Timestamps with minutes > 59 or seconds > 59 must be rejected with ParseIssue."""
    srt_bad_minutes = "1\n00:75:00,000 --> 00:75:02,000\nInvalid minutes\n"
    items = service.parse_subtitles(srt_bad_minutes, "srt")
    assert len(items) == 0
    issues = service.last_parse_issues
    assert any(i.kind == "invalid_timestamp" for i in issues)

    vtt_bad_seconds = (
        "WEBVTT\n\n00:01:99.000 --> 00:02:00.000\nInvalid seconds in VTT\n"
    )
    vtt_items = service.parse_subtitles(vtt_bad_seconds, "vtt")
    assert len(vtt_items) == 0
    assert any(i.kind == "invalid_timestamp" for i in service.last_parse_issues)


def test_reversed_timestamps_recorded_as_issue(service):
    """End time before start time must record reversed_timing ParseIssue."""
    srt_reversed = "1\n00:05:00,000 --> 00:02:00,000\nBackwards in time\n"
    items = service.parse_subtitles(srt_reversed, "srt")
    assert len(items) == 0
    issues = service.last_parse_issues
    assert any(i.kind == "reversed_timing" for i in issues)


def test_empty_cue_handling_across_all_formats(service):
    """Empty cues in SRT, VTT, and ASS must be captured as ParseIssue without crashing."""
    srt_empty = (
        "1\n00:00:01,000 --> 00:00:02,000\n\n2\n00:00:03,000 --> 00:00:04,000\nValid\n"
    )
    srt_items = service.parse_subtitles(srt_empty, "srt")
    assert len(srt_items) == 1
    assert srt_items[0].text == "Valid"
    assert any(i.kind == "empty_cue" for i in service.last_parse_issues)

    vtt_empty = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n\n00:00:03.000 --> 00:00:04.000\nValid VTT\n"
    vtt_items = service.parse_subtitles(vtt_empty, "vtt")
    assert len(vtt_items) == 1
    assert vtt_items[0].text == "Valid VTT"
    assert any(i.kind == "empty_cue" for i in service.last_parse_issues)

    ass_empty = """[Script Info]
Title: Empty Cue Test
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,
Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,Valid ASS
"""
    ass_items = service.parse_subtitles(ass_empty, "ass")
    assert len(ass_items) == 1
    assert ass_items[0].text == "Valid ASS"
    assert any(i.kind == "empty_cue" for i in service.last_parse_issues)


def test_batch_processing_isolates_failures_and_missing_files(qapp, tmp_path):
    """Batch queue must process valid files, isolate errors per file, and not crash."""
    win = MainWindow()

    valid_srt = tmp_path / "valid.srt"
    valid_srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nValid cue\n", encoding="utf-8"
    )

    missing_file = tmp_path / "missing.srt"

    empty_file = tmp_path / "empty.srt"
    empty_file.write_text("", encoding="utf-8")

    win._clear_batch_table()
    for f in [str(valid_srt), str(missing_file), str(empty_file)]:
        row = win.batch_table.rowCount()
        win.batch_table.insertRow(row)
        win.batch_table.setItem(row, 0, QTableWidgetItem(f))
        win.batch_table.setItem(row, 1, QTableWidgetItem("1 KB"))
        win.batch_table.setItem(row, 2, QTableWidgetItem("srt"))
        win.batch_table.setItem(row, 3, QTableWidgetItem("Queued"))

    win.toggle_translate.setChecked(False)
    win.toggle_clean.setChecked(True)

    win._run_batch_processing()
    _wait_for_batch(win, qapp)

    from application.services.i18n_service import t

    assert win.batch_table.item(0, 3).text() == t("batch.status_completed")
    out_path = str(tmp_path / "valid_processed.srt")
    assert os.path.exists(out_path)

    # Row 1 (missing file) must show error without stopping the batch
    expected_err_prefix = (
        t("batch.status_error", err="").split("{")[0].split(":")[0].strip()
    )
    assert expected_err_prefix.lower() in win.batch_table.item(1, 3).text().lower()

    # Row 2 (empty file) must complete safely (0 cues processed)
    assert win.batch_table.item(2, 3).text() == t("batch.status_completed")


def _wait_for_batch(window, qapp, timeout=15.0):
    """Batch work runs on a QThread (A-4): await it deterministically."""
    worker = getattr(window, "batch_worker", None)
    assert worker is not None, "batch worker was not started"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if not window._batch_running:
            break
        time.sleep(0.01)
    assert not window._batch_running, "batch timed out"
    assert worker.wait(int(timeout * 1000))
    qapp.processEvents()


def test_batch_processing_cooperative_cancellation(qapp, tmp_path):
    """Cancelling batch processing must halt further execution cleanly."""
    win = MainWindow()

    file1 = tmp_path / "f1.srt"
    file1.write_text("1\n00:00:01,000 --> 00:00:02,000\nCue 1\n", encoding="utf-8")
    file2 = tmp_path / "f2.srt"
    file2.write_text("1\n00:00:01,000 --> 00:00:02,000\nCue 2\n", encoding="utf-8")

    win._clear_batch_table()
    for f in [str(file1), str(file2)]:
        row = win.batch_table.rowCount()
        win.batch_table.insertRow(row)
        win.batch_table.setItem(row, 0, QTableWidgetItem(f))
        win.batch_table.setItem(row, 3, QTableWidgetItem("Queued"))

    win._batch_cancelled = True
    win._run_batch_processing()

    # Since cancelled before row 0, row 0 stays Queued
    assert win.batch_table.item(0, 3).text() == "Queued"


def test_process_worker_cancellation_during_clean_or_parse(tmp_path, qapp):
    """ProcessWorker must abort cooperatively when cancelled before or during stages."""
    source = tmp_path / "sample.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")

    service = SubtitleService()
    worker = ProcessWorker(
        service=service,
        file_path=str(source),
        do_clean=True,
        do_translate=False,
        target_lang="es",
        source_lang="auto",
        engine="google",
    )

    signals_emitted = []
    worker.cancelled.connect(lambda: signals_emitted.append("cancelled"))
    worker.completed.connect(lambda res: signals_emitted.append("completed"))

    worker.cancel()
    worker.run()

    assert "cancelled" in signals_emitted
    assert "completed" not in signals_emitted


def test_process_subtitles_cancel_event_without_translation(tmp_path):
    """SubtitleService.process_subtitles must raise SubtitleCancelledError when cancelled."""
    source = tmp_path / "in.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nText\n", encoding="utf-8")

    service = SubtitleService()
    event = threading.Event()
    event.set()

    with pytest.raises(SubtitleCancelledError):
        service.process_subtitles(
            file_path=str(source),
            do_clean=True,
            do_translate=False,
            cancel_event=event,
        )


def test_atomic_write_preserves_destination_on_failure(tmp_path, monkeypatch):
    """If atomic_write_text encounters a disk write error, destination remains intact."""
    dest = tmp_path / "important.srt"
    dest.write_text("ORIGINAL CONTENT", encoding="utf-8")

    def fail_fsync(fd):
        raise OSError("Simulated disk error during fsync")

    monkeypatch.setattr("os.fsync", fail_fsync)

    with pytest.raises(OSError, match="Simulated disk error"):
        atomic_write_text(str(dest), "NEW CORRUPTED CONTENT")

    # Destination MUST still contain original content
    assert dest.read_text(encoding="utf-8") == "ORIGINAL CONTENT"

    # Temporary files must be cleaned up
    remaining_tmps = [f for f in os.listdir(tmp_path) if f.startswith(".srt4u-tmp-")]
    assert len(remaining_tmps) == 0


def test_batch_processing_resets_cancellation_for_subsequent_runs(qapp, tmp_path):
    """Cancelling a batch must not prevent subsequent batch runs from executing."""
    win = MainWindow()

    win.cancel_batch()
    win._run_batch_processing()

    valid_file = tmp_path / "subsequent.srt"
    valid_file.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nSubsequent\n", encoding="utf-8"
    )

    win._clear_batch_table()
    win.batch_table.insertRow(0)
    win.batch_table.setItem(0, 0, QTableWidgetItem(str(valid_file)))
    win.batch_table.setItem(0, 1, QTableWidgetItem("1 KB"))
    win.batch_table.setItem(0, 2, QTableWidgetItem("srt"))
    win.batch_table.setItem(0, 3, QTableWidgetItem("Queued"))

    win.toggle_translate.setChecked(False)
    win.toggle_clean.setChecked(True)
    win._run_batch_processing()
    _wait_for_batch(win, qapp)

    from application.services.i18n_service import t

    assert win.batch_table.item(0, 3).text() == t("batch.status_completed")
    out_file = tmp_path / "subsequent_processed.srt"
    assert out_file.exists()


def test_batch_processing_reentrancy_guard(qapp, tmp_path):
    """Calling _run_batch_processing while already running must safely no-op."""
    win = MainWindow()
    win._batch_running = True

    valid_file = tmp_path / "reentrant.srt"
    valid_file.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nReentrant\n", encoding="utf-8"
    )

    win._clear_batch_table()
    win.batch_table.insertRow(0)
    win.batch_table.setItem(0, 0, QTableWidgetItem(str(valid_file)))
    win.batch_table.setItem(0, 3, QTableWidgetItem("Queued"))

    win._run_batch_processing()
    # Stays Queued because call returned immediately
    assert win.batch_table.item(0, 3).text() == "Queued"


def test_run_burn_in_sync_failure_before_temp_output_cleans_up_safely(
    tmp_path, monkeypatch
):
    """If burn-in preparation fails before temp_output is assigned, TypeError must not be raised."""
    from application.services.media_pipeline import run_burn_in_sync
    from application.services.video_burner_service import VideoBurnerService

    video = tmp_path / "dummy.mp4"
    video.write_bytes(b"dummy")

    monkeypatch.setattr(VideoBurnerService, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(VideoBurnerService, "get_video_duration_ms", lambda *a: 5000)
    monkeypatch.setattr(
        VideoBurnerService, "get_video_dimensions", lambda *a: (1920, 1080)
    )

    # Force generate_ass_script to raise an exception before temp_output is created
    def fail_ass(*args, **kwargs):
        raise RuntimeError("Simulated ASS generation failure")

    monkeypatch.setattr(VideoBurnerService, "generate_ass_script", fail_ass)

    with pytest.raises(RuntimeError, match="Simulated ASS generation failure"):
        run_burn_in_sync(
            video_path=str(video),
            items=[],
            output_path=str(tmp_path / "out.mp4"),
        )


def test_parallel_translation_cancelled_error_handling(monkeypatch):
    """If a future raises CancelledError during as_completed, translate_subtitles handles it as SubtitleCancelledError."""
    import concurrent.futures
    from application.services.subtitle_service import (
        SubtitleService,
        SubtitleItem,
        SubtitleCancelledError,
    )

    service = SubtitleService()
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="First"),
        SubtitleItem(index=2, start_ms=3000, end_ms=4000, text="Second"),
    ]

    class FakeFuture:
        def result(self):
            raise concurrent.futures.CancelledError()

        def cancel(self):
            return True

    def fake_as_completed(fs):
        return [FakeFuture()]

    monkeypatch.setattr(concurrent.futures, "as_completed", fake_as_completed)

    with pytest.raises(SubtitleCancelledError):
        service.translate_subtitles(items, target_language="es", parallel=True)


def test_subtitle_analytics_ignores_none_subtitle_index_for_rule_violations():
    """SubtitleAnalyticsService must not count findings with subtitle_index=None as affected cues."""
    from application.services.subtitle_qa import QAFinding, QAReport
    from application.services.subtitle_analytics import SubtitleAnalyticsService

    svc = SubtitleAnalyticsService()
    # A report with no cue index (e.g. global finding with rule name 'cps_exceeded')
    finding = QAFinding(
        severity="warning",
        rule="cps_exceeded",
        message="Global file warning",
        subtitle_index=None,
    )
    report = QAReport([finding])
    analytics = svc.analyze([], qa_report=report)

    assert analytics.timing.cps_violations == 0
    assert analytics.quality.line_length_violations == 0
    assert analytics.timing.overlapping_subtitles == 0


def test_burn_in_worker_cancelled_before_start(tmp_path, monkeypatch):
    """BurnInWorker cancelled before run() must emit cancelled and not run FFmpeg."""
    from application.services.video_burner_service import (
        BurnInWorker,
        BurnInOptions,
        VideoBurnerService,
    )
    from application.services.subtitle_service import SubtitleItem

    video = tmp_path / "vid.mp4"
    video.write_bytes(b"dummy")
    out = tmp_path / "out.mp4"

    monkeypatch.setattr(VideoBurnerService, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(VideoBurnerService, "get_video_duration_ms", lambda *a: 5000)
    monkeypatch.setattr(
        VideoBurnerService, "get_video_dimensions", lambda *a: (1920, 1080)
    )

    worker = BurnInWorker(
        video_path=str(video),
        output_path=str(out),
        subtitle_items=[SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hi")],
        options=BurnInOptions(),
    )
    cancelled_signals = []
    worker.cancelled.connect(lambda: cancelled_signals.append(True))

    worker.cancel()
    worker.run()

    assert len(cancelled_signals) == 1
    assert not out.exists()


def test_burn_in_worker_reaps_process_on_cancellation(tmp_path, monkeypatch):
    """BurnInWorker must terminate and wait on the child process when cancelled."""
    import subprocess
    from io import StringIO
    from application.services.video_burner_service import (
        BurnInWorker,
        BurnInOptions,
        VideoBurnerService,
    )
    from application.services.subtitle_service import SubtitleItem

    video = tmp_path / "vid.mp4"
    video.write_bytes(b"dummy")
    out = tmp_path / "out.mp4"

    monkeypatch.setattr(VideoBurnerService, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(VideoBurnerService, "get_video_duration_ms", lambda *a: 5000)
    monkeypatch.setattr(
        VideoBurnerService, "get_video_dimensions", lambda *a: (1920, 1080)
    )

    class MockProcess:
        def __init__(self, *args, **kwargs):
            self.stdout = StringIO("out_time_us=1000000\nprogress=continue\n")
            self.returncode = None
            self.terminated = False
            self.waited = False

        def poll(self):
            return 0 if self.terminated else None

        def readline(self):
            return self.stdout.readline()

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True
            self.returncode = -15
            return -15

        def kill(self):
            self.terminated = True

    mock_proc = None

    def mock_popen(*args, **kwargs):
        nonlocal mock_proc
        mock_proc = MockProcess(*args, **kwargs)
        return mock_proc

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    worker = BurnInWorker(
        video_path=str(video),
        output_path=str(out),
        subtitle_items=[SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hi")],
        options=BurnInOptions(),
    )

    cancelled_signals = []
    worker.cancelled.connect(lambda: cancelled_signals.append(True))

    def trigger_cancel(*args):
        worker.cancel()

    worker.progress_updated.connect(trigger_cancel)
    worker.run()

    assert len(cancelled_signals) == 1
    assert mock_proc is not None
    assert mock_proc.terminated is True
    assert mock_proc.waited is True


def test_run_burn_in_sync_reaps_process_on_exception(tmp_path, monkeypatch):
    """run_burn_in_sync must terminate and wait on FFmpeg if an exception occurs during loop."""
    import subprocess
    from application.services.media_pipeline import run_burn_in_sync
    from application.services.video_burner_service import VideoBurnerService
    from application.services.subtitle_service import SubtitleItem

    video = tmp_path / "vid.mp4"
    video.write_bytes(b"dummy")
    out = tmp_path / "out.mp4"

    monkeypatch.setattr(VideoBurnerService, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(VideoBurnerService, "get_video_duration_ms", lambda *a: 5000)
    monkeypatch.setattr(
        VideoBurnerService, "get_video_dimensions", lambda *a: (1920, 1080)
    )

    class MockFailingProcess:
        def __init__(self, *args, **kwargs):
            class BadStdout:
                def readline(self):
                    raise RuntimeError("Simulated stdout read error")

            self.stdout = BadStdout()
            self.returncode = None
            self.terminated = False
            self.waited = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True
            self.returncode = -15
            return -15

        def kill(self):
            self.terminated = True

    mock_proc = None

    def mock_popen(*args, **kwargs):
        nonlocal mock_proc
        mock_proc = MockFailingProcess(*args, **kwargs)
        return mock_proc

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    with pytest.raises(RuntimeError, match="Simulated stdout read error"):
        run_burn_in_sync(
            video_path=str(video),
            items=[SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hi")],
            output_path=str(out),
        )

    assert mock_proc is not None
    assert mock_proc.terminated is True
    assert mock_proc.waited is True


def test_burn_in_progress_modal_reject_cancels_worker(qapp, tmp_path, monkeypatch):
    """Rejecting BurnInProgressModal must cancel the active worker and wait."""
    from application.ui.burn_in_dialog import BurnInProgressModal, BurnInOptions
    from application.services.video_burner_service import BurnInWorker

    cancelled = []
    running = True

    def mock_cancel(self):
        nonlocal running
        cancelled.append(True)
        running = False

    monkeypatch.setattr(BurnInWorker, "start", lambda self: None)
    monkeypatch.setattr(BurnInWorker, "cancel", mock_cancel)
    monkeypatch.setattr(BurnInWorker, "isRunning", lambda self: running)
    monkeypatch.setattr(BurnInWorker, "wait", lambda self, timeout=None: True)

    modal = BurnInProgressModal(
        video_path=str(tmp_path / "vid.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        subtitle_items=[],
        options=BurnInOptions(),
    )
    modal.reject()
    assert len(cancelled) == 1


def test_main_window_active_workers_tracks_burn_modal(qapp):
    """MainWindow._active_workers must find workers on win.burn_modal."""
    win = MainWindow()
    assert len(win._active_workers()) == 0

    class DummyModal:
        class DummyWorker:
            def isRunning(self):
                return True

            def isFinished(self):
                return False

        worker = DummyWorker()

    win.burn_modal = DummyModal()
    workers = win._active_workers()
    assert len(workers) == 1
    assert workers[0] is win.burn_modal.worker

    # Also track directly via win.burn_worker even if win.burn_modal is dismissed (set to None)
    win.burn_worker = win.burn_modal.worker
    win.burn_modal = None
    workers_after_modal_dismissed = win._active_workers()
    assert len(workers_after_modal_dismissed) == 1
    assert workers_after_modal_dismissed[0] is win.burn_worker

    # Deduplication test: when both burn_worker and burn_modal refer to same worker
    win.burn_modal = DummyModal()
    win.burn_modal.worker = win.burn_worker
    assert len(win._active_workers()) == 1


def test_batch_processing_immediate_cancellation_mid_process(
    qapp, tmp_path, monkeypatch
):
    """Cancelling batch during process_subtitles immediately aborts without continuing."""
    win = MainWindow()

    f1 = tmp_path / "file1.srt"
    f1.write_text("1\n00:00:01,000 --> 00:00:02,000\nF1\n", encoding="utf-8")
    f2 = tmp_path / "file2.srt"
    f2.write_text("1\n00:00:01,000 --> 00:00:02,000\nF2\n", encoding="utf-8")

    win._clear_batch_table()
    for f in [str(f1), str(f2)]:
        row = win.batch_table.rowCount()
        win.batch_table.insertRow(row)
        win.batch_table.setItem(row, 0, QTableWidgetItem(f))
        win.batch_table.setItem(row, 3, QTableWidgetItem("Queued"))

    def mock_process(*args, **kwargs):
        win.cancel_batch()
        raise SubtitleCancelledError("cancelled during process")

    monkeypatch.setattr(win.subtitle_service, "process_subtitles", mock_process)

    win._run_batch_processing()
    _wait_for_batch(win, qapp)

    from application.services.i18n_service import t

    assert win.batch_table.item(0, 3).text() == t("batch.status_error", err="cancelled")
    assert win.batch_table.item(1, 3).text() == "Queued"
    assert win._batch_running is False
    assert win._batch_cancelled is False


def test_cross_format_roundtrip_all_formats(service):
    """Subtitles must round-trip cleanly across SRT -> ASS -> VTT -> SSA -> TXT."""
    srt_content = (
        "1\n00:01:00,000 --> 00:01:05,000\nFirst dialogue line\n\n"
        "2\n00:02:00,500 --> 00:02:04,750\nSecond dialogue line\n"
    )
    items_srt = service.parse_subtitles(srt_content, "srt")
    assert len(items_srt) == 2

    ass_rendered = service.format_output(items_srt, "ass")
    items_ass = service.parse_subtitles(ass_rendered, "ass")
    assert len(items_ass) == 2
    assert items_ass[0].text == "First dialogue line"
    assert items_ass[1].start_ms == items_srt[1].start_ms

    vtt_rendered = service.format_output(items_ass, "vtt")
    items_vtt = service.parse_subtitles(vtt_rendered, "vtt")
    assert len(items_vtt) == 2
    assert items_vtt[0].text == "First dialogue line"

    ssa_rendered = service.format_output(items_vtt, "ssa")
    items_ssa = service.parse_subtitles(ssa_rendered, "ssa")
    assert len(items_ssa) == 2
    assert items_ssa[1].text == "Second dialogue line"

    txt_rendered = service.format_output(items_ssa, "txt")
    items_txt = service.parse_subtitles(txt_rendered, "txt")
    assert len(items_txt) == 2
    assert "First dialogue line" in items_txt[0].text
    assert "Second dialogue line" in items_txt[1].text
