"""Tests for the hidden ``--smoke-test`` mode of the application entry point.

The packaged-artifact CI job runs the same function through the built
executable; these tests exercise it in-process under the offscreen Qt platform.
"""

import os
import sys

import pytest

import main
from application.services.config_service import ConfigService
from application.services.video_burner_service import VideoBurnerService


@pytest.fixture
def smoke_env(monkeypatch):
    # monkeypatch records the current values so the function's process-wide
    # changes (config directory, history path) are restored after each test.
    monkeypatch.setenv("SRT4U_HISTORY_DB", os.devnull)
    monkeypatch.setattr(ConfigService, "_get_config_dir", ConfigService._get_config_dir)
    return monkeypatch


def test_smoke_mode_passes_with_real_runtime(qapp, smoke_env):
    assert main.run_smoke_test() == 0


def test_smoke_mode_fails_when_ffmpeg_is_missing(qapp, smoke_env):
    smoke_env.setattr(
        VideoBurnerService, "get_ffmpeg_path", classmethod(lambda cls: None)
    )
    assert main.run_smoke_test() == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell stub")
def test_smoke_mode_fails_when_ffmpeg_does_not_run(qapp, smoke_env, tmp_path):
    broken = tmp_path / "ffmpeg"
    broken.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    broken.chmod(0o755)
    smoke_env.setattr(
        VideoBurnerService, "get_ffmpeg_path", classmethod(lambda cls: str(broken))
    )
    assert main.run_smoke_test() == 1


def test_smoke_log_records_failure_reason(qapp, smoke_env):
    smoke_env.setattr(
        VideoBurnerService, "get_ffmpeg_path", classmethod(lambda cls: None)
    )
    assert main.run_smoke_test() == 1
    log_path = os.path.join(main.tempfile.gettempdir(), main.SMOKE_LOG_NAME)
    with open(log_path, encoding="utf-8") as handle:
        assert "FAILED: FFmpeg not found" in handle.read()
