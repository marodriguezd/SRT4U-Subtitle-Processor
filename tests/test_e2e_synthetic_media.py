"""Portable end-to-end tests on a synthetic video generated at test time.

Unlike ``test_e2e_real_media.py`` these tests need no private fixture: a short
black clip with a sine tone is produced by FFmpeg into a pytest temporary
directory, subtitles are burned in through the headless pipeline entry point
(``run_burn_in_sync``), and the output is validated with ``ffprobe`` and by
decoding frames. Each test skips only when a specific FFmpeg capability it
needs is missing; a media failure after a test has started is a real failure.
"""

import os
import shutil
import subprocess

import pytest

from application.services.media_pipeline import PipelineStageError, run_burn_in_sync
from application.services.subtitle_service import SubtitleService

VIDEO_W, VIDEO_H = 320, 240
VIDEO_SECONDS = 4

# Cue timings in ms. The gap 1400-2200 must stay empty after burn-in.
SRT_TEXT = """1
00:00:00,300 --> 00:00:01,400
Line one
Line two

2
00:00:02,200 --> 00:00:03,400
Second cue

3
00:00:03,400 --> 00:00:03,900
Third
"""


def _which(name):
    return shutil.which(name)


def _encoder_available(ffmpeg, name):
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    return f" {name} " in out


def _filter_available(ffmpeg, name):
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    return f" {name} " in out


@pytest.fixture(scope="module")
def ffmpeg_tools():
    ffmpeg = _which("ffmpeg")
    ffprobe = _which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe not found on PATH")
    if not _encoder_available(ffmpeg, "libx264") or not _encoder_available(
        ffmpeg, "aac"
    ):
        pytest.skip("FFmpeg lacks libx264 and/or aac encoders needed for the fixture")
    if not _filter_available(ffmpeg, "ass") and not _filter_available(
        ffmpeg, "subtitles"
    ):
        pytest.skip(
            "FFmpeg lacks the libass 'ass'/'subtitles' filter needed for burn-in"
        )
    return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}


@pytest.fixture(scope="module")
def synthetic_video(ffmpeg_tools, tmp_path_factory):
    """Generate a deterministic 4 s black clip with a 440 Hz tone (mp4)."""
    directory = tmp_path_factory.mktemp("synthetic_media")
    path = str(directory / "synthetic.mp4")
    cmd = [
        ffmpeg_tools["ffmpeg"],
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={VIDEO_W}x{VIDEO_H}:r=25:d={VIDEO_SECONDS}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=16000:duration={VIDEO_SECONDS}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return path


@pytest.fixture(scope="module")
def synthetic_srt(tmp_path_factory):
    path = tmp_path_factory.mktemp("synthetic_srt") / "synthetic.srt"
    path.write_text(SRT_TEXT, encoding="utf-8")
    return str(path)


def _probe(ffprobe, path):
    import json

    out = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _gray_frame_at(ffmpeg, path, seconds):
    """Decode one frame at ``seconds`` as raw 8-bit grayscale bytes."""
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            path,
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


def _bright_pixels(frame: bytes, threshold: int = 120) -> int:
    return sum(1 for value in frame if value > threshold)


def test_parse_synthetic_srt_keeps_cues_multiline_and_gap(synthetic_srt):
    with open(synthetic_srt, encoding="utf-8") as handle:
        items = SubtitleService().parse_subtitles(handle.read(), "srt")
    assert len(items) == 3
    assert "Line one" in items[0].text and "Line two" in items[0].text
    assert items[0].start_ms == 300 and items[0].end_ms == 1400
    # The 800 ms gap between the first and second cue is preserved.
    assert items[1].start_ms - items[0].end_ms == 800


def test_probe_synthetic_video_metadata(ffmpeg_tools, synthetic_video):
    data = _probe(ffmpeg_tools["ffprobe"], synthetic_video)
    streams = {s["codec_type"]: s for s in data["streams"]}
    assert streams["video"]["width"] == VIDEO_W
    assert streams["video"]["height"] == VIDEO_H
    assert "audio" in streams
    assert abs(float(data["format"]["duration"]) - VIDEO_SECONDS) < 0.5


def test_burn_in_renders_subtitles_and_keeps_gap_empty(
    ffmpeg_tools, synthetic_video, synthetic_srt, tmp_path
):
    with open(synthetic_srt, encoding="utf-8") as handle:
        items = SubtitleService().parse_subtitles(handle.read(), "srt")
    source_before = open(synthetic_video, "rb").read()
    output = str(tmp_path / "burned.mp4")

    result = run_burn_in_sync(synthetic_video, items, output)

    assert result == output
    assert os.path.getsize(output) > 0
    data = _probe(ffmpeg_tools["ffprobe"], output)
    streams = {s["codec_type"]: s for s in data["streams"]}
    assert streams["video"]["width"] == VIDEO_W
    assert streams["video"]["height"] == VIDEO_H
    assert "audio" in streams
    assert abs(float(data["format"]["duration"]) - VIDEO_SECONDS) < 0.5

    ffmpeg = ffmpeg_tools["ffmpeg"]
    # Inside the first cue the burned text produces bright pixels.
    assert _bright_pixels(_gray_frame_at(ffmpeg, output, 0.8)) > 20
    # In the intentional gap (1.4 s - 2.2 s) no subtitle may appear.
    assert _bright_pixels(_gray_frame_at(ffmpeg, output, 1.8)) == 0
    # The source video must be left untouched.
    assert open(synthetic_video, "rb").read() == source_before


def test_invalid_video_fails_cleanly_without_partial_output(
    ffmpeg_tools, synthetic_srt, tmp_path
):
    with open(synthetic_srt, encoding="utf-8") as handle:
        items = SubtitleService().parse_subtitles(handle.read(), "srt")
    bogus = tmp_path / "not_a_video.mp4"
    bogus.write_bytes(b"this is not a video container" * 20)
    output = str(tmp_path / "broken_out.mp4")

    with pytest.raises(PipelineStageError):
        run_burn_in_sync(str(bogus), items, output)

    assert not os.path.exists(output)
    leftovers = [name for name in os.listdir(tmp_path) if "srt4u-burn-tmp" in name]
    assert leftovers == []
