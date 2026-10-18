"""Regression tests for FFmpeg burn-in temporary file uniqueness, atomic replacement,
concurrency safety, and error cleanup.
"""

import concurrent.futures
import os
import subprocess
from pathlib import Path

import pytest

from application.services.i18n_service import t
from application.services.media_pipeline import (
    PipelineStageError,
    STAGE_BURN,
    run_burn_in_sync,
)
from application.services.subtitle_service import SubtitleItem
from application.services.video_burner_service import (
    BurnInOptions,
    BurnInWorker,
    VideoBurnerService,
    acquire_burn_destination,
    make_unique_burn_temp,
    release_burn_destination,
)


def test_make_unique_burn_temp_properties(tmp_path):
    dest = str(tmp_path / "output.mp4")
    temp1 = make_unique_burn_temp(dest)
    temp2 = make_unique_burn_temp(dest)

    assert temp1 != temp2, "Consecutive calls must produce unique filenames"
    assert os.path.dirname(temp1) == os.path.abspath(str(tmp_path))
    assert temp1.endswith(".mp4"), "Must preserve target format extension for FFmpeg"
    assert "srt4u-burn-tmp" in temp1, "Must contain substring for cleanup tracking"

    # Test with different extension
    mkv_dest = str(tmp_path / "movie.mkv")
    temp_mkv = make_unique_burn_temp(mkv_dest)
    assert temp_mkv.endswith(".mkv")

    # Generate 50 unique names and ensure no collisions
    generated = {make_unique_burn_temp(dest) for _ in range(50)}
    assert len(generated) == 50


def test_destination_lock_lifecycle(tmp_path):
    dest = str(tmp_path / "target.mp4")
    # Initial acquire succeeds
    assert acquire_burn_destination(dest) is True
    # Duplicate acquire on same destination fails
    assert acquire_burn_destination(dest) is False

    # Relative path pointing to same canonical file also fails
    rel_dest = os.path.relpath(dest)
    assert acquire_burn_destination(rel_dest) is False

    # Release allows subsequent acquisition
    release_burn_destination(dest)
    assert acquire_burn_destination(dest) is True
    release_burn_destination(dest)

    # Safe to release unacquired path
    release_burn_destination(dest)


def test_destination_lock_thread_safety(tmp_path):
    dest = str(tmp_path / "shared.mp4")
    successes = []

    def try_acquire():
        if acquire_burn_destination(dest):
            successes.append(True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(try_acquire) for _ in range(10)]
        concurrent.futures.wait(futures)

    try:
        assert len(successes) == 1, (
            "Exactly one thread must succeed in acquiring destination"
        )
    finally:
        release_burn_destination(dest)


def test_burn_in_worker_destination_collision(qapp, tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake-video-content")
    out = str(tmp_path / "collision_out.mp4")

    # Lock destination externally as if another worker/pipeline is running
    assert acquire_burn_destination(out) is True

    try:
        items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="test")]
        worker = BurnInWorker(str(video), out, items, BurnInOptions())
        events = {"failed": None}
        worker.failed.connect(lambda err: events.__setitem__("failed", err))

        worker.run()

        # Worker must have failed with prepare error without proceeding
        assert events["failed"] == t("burn.error_prepare")
        # No temporary files created
        leftovers = [n for n in os.listdir(tmp_path) if "srt4u-burn-tmp" in n]
        assert leftovers == []
    finally:
        release_burn_destination(out)


def test_run_burn_in_sync_destination_collision(tmp_path, monkeypatch):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake-video-content")
    out = str(tmp_path / "sync_collision_out.mp4")

    monkeypatch.setattr(
        VideoBurnerService, "get_ffmpeg_path", lambda: "/usr/bin/ffmpeg"
    )
    assert acquire_burn_destination(out) is True

    try:
        items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="test")]
        with pytest.raises(PipelineStageError) as exc_info:
            run_burn_in_sync(str(video), items, out)

        assert exc_info.value.stage == STAGE_BURN
        assert exc_info.value.error_type == "destination_busy"
        assert "already in progress" in str(exc_info.value)
    finally:
        release_burn_destination(out)


def test_run_burn_in_sync_failure_cleans_temp_and_releases_lock(tmp_path, monkeypatch):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake-video-content")
    out = str(tmp_path / "fail_cleanup_out.mp4")
    Path(out).write_bytes(b"original-valid-content")

    monkeypatch.setattr(
        VideoBurnerService, "get_ffmpeg_path", lambda: "/usr/bin/ffmpeg"
    )
    monkeypatch.setattr(
        VideoBurnerService, "get_video_duration_ms", lambda *args, **kwargs: 2000
    )
    monkeypatch.setattr(
        VideoBurnerService, "get_video_dimensions", lambda *args, **kwargs: (1920, 1080)
    )

    class MockFailingProcess:
        returncode = 1
        stdout = None

        def __init__(self, *args, **kwargs):
            import io

            self.stdout = io.StringIO("")

        def wait(self, timeout=None):
            return 1

        def poll(self):
            return 1

        def terminate(self):
            pass

        def kill(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", MockFailingProcess)

    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="test")]
    with pytest.raises(PipelineStageError) as exc_info:
        run_burn_in_sync(str(video), items, out)

    assert exc_info.value.error_type == "burn_in_error"

    # Pre-existing file survives intact
    assert Path(out).read_bytes() == b"original-valid-content"
    # No temporary files left behind
    leftovers = [n for n in os.listdir(tmp_path) if "srt4u-burn-tmp" in n]
    assert leftovers == []
    # Lock was released so subsequent acquire succeeds
    assert acquire_burn_destination(out) is True
    release_burn_destination(out)


def test_burn_in_worker_cancel_cleans_temp_and_releases_lock(
    qapp, tmp_path, monkeypatch
):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake-video-content")
    out = str(tmp_path / "cancel_cleanup_out.mp4")
    Path(out).write_bytes(b"previous-good-content")

    monkeypatch.setattr(
        VideoBurnerService, "get_ffmpeg_path", lambda: "/usr/bin/ffmpeg"
    )
    monkeypatch.setattr(
        VideoBurnerService, "get_video_duration_ms", lambda *args, **kwargs: 2000
    )
    monkeypatch.setattr(
        VideoBurnerService, "get_video_dimensions", lambda *args, **kwargs: (1920, 1080)
    )

    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="test")]
    worker = BurnInWorker(str(video), out, items, BurnInOptions())
    worker._is_cancelled = True

    events = {"cancelled": False, "failed": False}
    worker.cancelled.connect(lambda: events.__setitem__("cancelled", True))
    worker.failed.connect(lambda _err: events.__setitem__("failed", True))

    worker.run()

    assert events["cancelled"] is True
    assert events["failed"] is False
    assert Path(out).read_bytes() == b"previous-good-content"
    leftovers = [n for n in os.listdir(tmp_path) if "srt4u-burn-tmp" in n]
    assert leftovers == []
    # Destination lock was cleanly released
    assert acquire_burn_destination(out) is True
    release_burn_destination(out)
