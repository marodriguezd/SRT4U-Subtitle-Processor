"""Regression tests for the remediation pass over the independent audit.

Covers: D1 (atomic burn-in output), D2 (ASS per-cue style assignment),
D3 (WebVTT NOTE/STYLE/REGION blocks), D4 (parser/QA shared grammar),
D5 (API safe_detail for PipelineConfigError), D6 (GUI double-start guard)
and P1 (parse-issue propagation across layers).

D1 tests exercise the real FFmpeg binary when one is available; they skip
cleanly otherwise (matching the convention in tests/test_video_burner.py).
"""

import os
import shutil
import subprocess
import tempfile
import threading
import time

import pytest
from PyQt6.QtCore import QCoreApplication

from application.services import ass_utils
from application.services.ass_utils import build_ass_document
from application.services.media_pipeline import (
    MediaPipeline,
    PipelineConfig,
    PipelineStageError,
)
from application.services.subtitle_qa import SubtitleQA
from application.services.subtitle_service import (
    SubtitleItem,
    SubtitleService,
)
from application.services.timestamps import (
    ass_timestamp_to_ms,
    parse_timestamp_to_ms,
    srt_timestamp_to_ms,
    vtt_timestamp_to_ms,
)
from application.services.translation_providers import (
    ProviderRegistry,
    ProviderResponse,
    TranslationProvider,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

SAMPLE_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHello world\n"


class FakeProvider(TranslationProvider):
    name = "fake"
    model = "test-model"

    def translate(self, text, source_language, target_language, *, context=None):
        return "Hola mundo"

    def translate_detailed(
        self, text, source_language, target_language, *, context=None
    ):
        return ProviderResponse("Hola mundo", model=self.model)


@pytest.fixture
def mock_provider(monkeypatch):
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: FakeProvider()
    )


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from application.api.app import create_app
    from application.api.jobs import JobManager

    app = create_app(job_manager=JobManager(max_workers=2))
    with TestClient(app) as test_client:
        yield test_client


def _upload(
    client, path="/api/v1/analyze", content=SAMPLE_SRT, filename="in.srt", **data
):
    return client.post(
        path, files={"file": (filename, content, "text/plain")}, data=data
    )


def _wait_job(client, job_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not finish")


def _ffmpeg():
    from application.services.video_burner_service import VideoBurnerService

    return VideoBurnerService.get_ffmpeg_path()


def _make_video(ffmpeg, path, seconds):
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={seconds}:size=320x240:rate=10",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ================================================================== D1 =====


@pytest.fixture(scope="module")
def real_video():
    """One shared input video; skipped when FFmpeg is not available.

    Long enough that even a very fast encode keeps running past the cancel
    point in the D1 tests.
    """
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("FFmpeg no está disponible en este entorno")
    tmpdir = tempfile.mkdtemp(prefix="srt4u_d1_")
    path = os.path.join(tmpdir, "input_long.mp4")
    _make_video(ffmpeg, path, 600)
    yield path
    shutil.rmtree(tmpdir, ignore_errors=True)


def _run_with_cancel(video_path, output_path, delay):
    items = [SubtitleItem(index=1, start_ms=0, end_ms=2000, text="hola")]
    cancel = threading.Event()

    def fire():
        time.sleep(delay)
        cancel.set()

    threading.Thread(target=fire, daemon=True).start()
    from application.services.media_pipeline import run_burn_in_sync

    with pytest.raises(Exception) as excinfo:
        run_burn_in_sync(video_path, items, output_path, cancel_event=cancel)
    return excinfo


def test_d1_cancel_preserves_preexisting_output(real_video):
    """D1-1: cancel mid-encode must leave the pre-existing output untouched."""
    out = real_video.replace("input_long.mp4", "d1_cancel_out.mp4")
    _make_video(_ffmpeg(), out, 5)
    good = open(out, "rb").read()
    _run_with_cancel(real_video, out, delay=1.0)
    assert os.path.exists(out), "cancel must not remove the previous output"
    assert open(out, "rb").read() == good, "previous output must be byte-identical"
    leftovers = [n for n in os.listdir(os.path.dirname(out)) if "srt4u-burn-tmp" in n]
    assert leftovers == [], "cancelled encode must not leave temp files"


def test_d1_ffmpeg_failure_preserves_preexisting_output(real_video):
    """D1-2: a non-zero FFmpeg exit must leave the pre-existing output intact.

    The failure is injected at the FFmpeg invocation boundary (the real
    binary exits non-zero on the bogus filter) so the cleanup semantics are
    the production ones.
    """
    from application.services import media_pipeline as mp

    out = real_video.replace("input_long.mp4", "d1_fail_out.mp4")
    _make_video(_ffmpeg(), out, 5)
    good = open(out, "rb").read()

    real_popen = subprocess.Popen
    popen_calls = []

    def failing_popen(cmd, *args, **kwargs):
        popen_calls.append(cmd)
        sabotaged = list(cmd)
        if "-vf" in sabotaged:
            sabotaged[sabotaged.index("-vf") + 1] = "ass=definitely_missing.ass"
        return real_popen(sabotaged, *args, **kwargs)

    original = mp.subprocess.Popen
    mp.subprocess.Popen = failing_popen
    try:
        items = [SubtitleItem(index=1, start_ms=0, end_ms=2000, text="hola")]
        with pytest.raises(PipelineStageError):
            mp.run_burn_in_sync(real_video, items, out)
    finally:
        mp.subprocess.Popen = original
    assert popen_calls, "FFmpeg must have been invoked"
    assert os.path.exists(out), "failed encode must not remove the output"
    assert open(out, "rb").read() == good
    leftovers = [n for n in os.listdir(os.path.dirname(out)) if "srt4u-burn-tmp" in n]
    assert leftovers == []


def test_d1_no_partial_output_after_failure_without_previous(real_video):
    """D1-3: failure with no previous output leaves no partial final file."""
    from application.services import media_pipeline as mp

    out = real_video.replace("input_long.mp4", "d1_noprev_out.mp4")
    assert not os.path.exists(out)
    real_popen = subprocess.Popen

    def failing_popen(cmd, *args, **kwargs):
        sabotaged = list(cmd)
        if "-vf" in sabotaged:
            sabotaged[sabotaged.index("-vf") + 1] = "ass=definitely_missing.ass"
        return real_popen(sabotaged, *args, **kwargs)

    original = mp.subprocess.Popen
    mp.subprocess.Popen = failing_popen
    try:
        items = [SubtitleItem(index=1, start_ms=0, end_ms=2000, text="hola")]
        with pytest.raises(PipelineStageError):
            mp.run_burn_in_sync(real_video, items, out)
    finally:
        mp.subprocess.Popen = original
    assert not os.path.exists(out), "no partial final output may remain"


def test_d1_success_promotes_temp_to_final(real_video):
    """D1-4: a successful encode atomically produces the final output."""
    from application.services.media_pipeline import run_burn_in_sync

    out = real_video.replace("input_long.mp4", "d1_ok_out.mp4")
    items = [SubtitleItem(index=1, start_ms=0, end_ms=2000, text="hola")]
    result = run_burn_in_sync(real_video, items, out)
    assert result == out
    assert os.path.exists(out) and os.path.getsize(out) > 0
    leftovers = [n for n in os.listdir(os.path.dirname(out)) if "srt4u-burn-tmp" in n]
    assert leftovers == []


def test_d1_success_replaces_previous_output(real_video):
    """D1-4b: a successful encode replaces a previous output atomically."""
    from application.services.media_pipeline import run_burn_in_sync

    out = real_video.replace("input_long.mp4", "d1_replace_out.mp4")
    _make_video(_ffmpeg(), out, 5)
    old_size = os.path.getsize(out)
    items = [SubtitleItem(index=1, start_ms=0, end_ms=2000, text="hola")]
    run_burn_in_sync(real_video, items, out)
    assert os.path.getsize(out) != old_size
    leftovers = [n for n in os.listdir(os.path.dirname(out)) if "srt4u-burn-tmp" in n]
    assert leftovers == []


def _run_worker_to_completion(worker, events, timeout=60):
    """Start a BurnInWorker and pump Qt events so its signals are delivered.

    With no running event loop the queued connections would never be
    dispatched; pumping ``processEvents`` while the thread runs is the
    event-loop-free equivalent of what the real dialog does.
    """
    worker.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if worker.isFinished():
            break
        time.sleep(0.02)
    QCoreApplication.processEvents()
    return events


def test_d1_burnin_worker_cancel_preserves_preexisting_output(qapp, real_video):
    """D1-5: the Qt worker path must honor the same output-integrity contract."""
    from application.services.video_burner_service import (
        BurnInOptions,
        BurnInWorker,
    )

    out = real_video.replace("input_long.mp4", "d1_worker_out.mp4")
    _make_video(_ffmpeg(), out, 5)
    good = open(out, "rb").read()
    items = [SubtitleItem(index=1, start_ms=0, end_ms=2000, text="hola")]
    worker = BurnInWorker(real_video, out, items, BurnInOptions())
    events = {"cancelled": False, "failed": False, "success": None}
    worker.cancelled.connect(lambda: events.__setitem__("cancelled", True))
    worker.failed.connect(lambda _msg: events.__setitem__("failed", True))
    worker.finished_success.connect(lambda p: events.__setitem__("success", p))
    worker.start()
    # Pump events while the encode starts, then cancel mid-write.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not worker.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.02)
    time.sleep(1.0)  # encoding is now writing into the temp file
    worker.cancel()
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if worker.isFinished():
            break
        time.sleep(0.02)
    QCoreApplication.processEvents()
    assert worker.isFinished(), "worker must stop after cancel"
    assert events["cancelled"] and not events["failed"] and events["success"] is None
    assert os.path.exists(out), "worker cancel must not remove the output"
    assert open(out, "rb").read() == good
    leftovers = [n for n in os.listdir(os.path.dirname(out)) if "srt4u-burn-tmp" in n]
    assert leftovers == []
    worker.deleteLater()


def test_d1_burnin_worker_ffmpeg_failure_preserves_preexisting_output(
    qapp, real_video, monkeypatch
):
    """D1-5b: worker + non-zero FFmpeg exit leaves the previous output intact."""
    from application.services import video_burner_service as vbs
    from application.services.video_burner_service import BurnInOptions, BurnInWorker

    out = real_video.replace("input_long.mp4", "d1_workerfail_out.mp4")
    _make_video(_ffmpeg(), out, 5)
    good = open(out, "rb").read()

    real_popen = subprocess.Popen

    def failing_popen(cmd, *args, **kwargs):
        sabotaged = list(cmd)
        if "-vf" in sabotaged:
            sabotaged[sabotaged.index("-vf") + 1] = "ass=definitely_missing.ass"
        return real_popen(sabotaged, *args, **kwargs)

    monkeypatch.setattr(vbs.subprocess, "Popen", failing_popen)

    items = [SubtitleItem(index=1, start_ms=0, end_ms=2000, text="hola")]
    worker = BurnInWorker(real_video, out, items, BurnInOptions())
    events = {"cancelled": False, "failed": False, "success": None}
    worker.cancelled.connect(lambda: events.__setitem__("cancelled", True))
    worker.failed.connect(lambda _msg: events.__setitem__("failed", True))
    worker.finished_success.connect(lambda p: events.__setitem__("success", p))
    worker.start()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if worker.isFinished():
            break
        time.sleep(0.02)
    QCoreApplication.processEvents()
    assert worker.isFinished(), "worker must finish even when FFmpeg fails"
    assert events["failed"] and events["success"] is None
    assert os.path.exists(out)
    assert open(out, "rb").read() == good
    leftovers = [n for n in os.listdir(os.path.dirname(out)) if "srt4u-burn-tmp" in n]
    assert leftovers == []
    worker.deleteLater()


# ================================================================== D2 =====


def _dialogue_style_fields(document):
    return [
        line.split(",")[3]
        for line in document.splitlines()
        if line.startswith("Dialogue:")
    ]


TOP_BOTTOM_DOC = (
    "[Script Info]\nTitle: t\nScriptType: v4.00+\n\n[V4+ Styles]\n"
    "Format: " + ass_utils.STYLE_FORMAT + "\n"
    "Style: Top,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
    "100,100,0,0,1,3,3,8,10,10,60,1\n"
    "Style: Bottom,Arial,36,&H0000FFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
    "100,100,0,0,3,10,0,2,10,10,40,1\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:02.00,Top,,0,0,0,,top line\n"
    "Dialogue: 0,0:00:03.00,0:00:04.00,Bottom,,0,0,0,,bottom line\n"
)


def test_d2_ass_export_preserves_per_cue_style_assignment():
    """D2: Top/Bottom cues must survive export as Top/Bottom, not all Default."""
    service = SubtitleService()
    items = service.parse_subtitles(TOP_BOTTOM_DOC, "ass")
    assert [item.style for item in items] == ["Top", "Bottom"]

    exported = service.format_output(items, "ass")
    styles = _dialogue_style_fields(exported)
    assert styles == ["Top", "Bottom"], (
        f"style assignment lost: {styles}; every Dialogue collapsed to Default"
    )


def test_d2_style_assignment_survives_clean_round_trip():
    """D2: the assignment must survive the normal processing pipeline too."""
    service = SubtitleService()
    items = service.parse_subtitles(TOP_BOTTOM_DOC, "ass")
    cleaned, _total, _removed = service.clean_subtitles(items)
    exported = service.format_output(cleaned, "ass")
    assert _dialogue_style_fields(exported) == ["Top", "Bottom"]


def test_d2_export_and_burnin_render_same_text_with_styles_declared():
    """D2/M1: text rendering stays shared; every referenced style is declared."""
    service = SubtitleService()
    items = service.parse_subtitles(TOP_BOTTOM_DOC, "ass")
    exported = service.format_output(items, "ass")

    def declared(document):
        names = set()
        for line in document.splitlines():
            if line.startswith("Style:"):
                names.add(line.split(":", 1)[1].split(",")[0].strip())
        return names

    referenced = set(_dialogue_style_fields(exported))
    assert referenced <= declared(exported), "undefined style referenced"
    # Burn-in text bodies remain byte-identical to the exporter's (M1).
    from application.services.video_burner_service import (
        BurnInOptions,
        VideoBurnerService,
    )

    burned = VideoBurnerService.generate_ass_script(
        items, BurnInOptions(), video_width=640, video_height=360
    )

    def bodies(doc):
        return [
            line.split(",", 9)[9]
            for line in doc.splitlines()
            if line.startswith("Dialogue:")
        ]

    assert bodies(exported) == bodies(burned)


def test_d2_build_ass_document_event_styles_parameter():
    """D2: the builder honours event_styles and falls back safely."""
    events = [(0, 1000, "one"), (1000, 2000, "two")]
    top_body = (
        "Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
        "100,100,0,0,1,2,2,2,10,10,10,1"
    )
    doc = build_ass_document(
        events,
        {"Top": top_body, "Bottom": top_body},
        event_styles=["Top", "Bottom"],
    )
    assert _dialogue_style_fields(doc) == ["Top", "Bottom"]
    # An unknown name falls back to Default; an unsafe name likewise.
    unsafe = build_ass_document(
        events,
        None,
        event_styles=["bad,name", None],
    )
    fields = _dialogue_style_fields(unsafe)
    assert fields == ["Default", "Default"]
    assert "Style: bad" not in unsafe


# ================================================================== D3 =====


def test_d3_note_block_with_timestamp_is_not_a_cue():
    service = SubtitleService()
    vtt = (
        "WEBVTT\n\n"
        "NOTE this is a translator comment\n"
        "the original file had cues at:\n"
        "00:00:01.000 --> 00:00:02.000\n"
        "which must not become a cue\n\n"
        "1\n00:00:05.000 --> 00:00:06.000\nReal cue\n"
    )
    items = service.parse_subtitles(vtt, "vtt")
    assert [(i.start_ms, i.text) for i in items] == [(5000, "Real cue")]
    assert service.last_parse_issues == []


def test_d3_style_and_region_blocks_are_consumed_whole():
    service = SubtitleService()
    vtt = (
        "WEBVTT\n\n"
        "STYLE\n::cue {\n  color: red;\n}\n00:00:03.000 --> 00:00:04.000 fake\n\n"
        "REGION\nid:fred width:40%\n00:00:05.000 --> 00:00:06.000 fake\n\n"
        "1\n00:00:07.000 --> 00:00:08.000\nReal cue\n"
    )
    items = service.parse_subtitles(vtt, "vtt")
    assert [(i.start_ms, i.text) for i in items] == [(7000, "Real cue")]
    assert service.last_parse_issues == []


def test_d3_metadata_block_directly_before_cue():
    service = SubtitleService()
    vtt = (
        "WEBVTT\n\n"
        "NOTE\nmulti line\n00:00:00.500 --> 00:00:00.600\nbody\n\n"
        "1\n00:00:01.000 --> 00:00:02.000\nFirst real\n"
    )
    items = service.parse_subtitles(vtt, "vtt")
    assert [i.text for i in items] == ["First real"]
    assert service.last_parse_issues == []


def test_d3_unterminated_metadata_block_consumes_rest_of_file():
    """A NOTE never closed by a blank line swallows the remainder (WebVTT spec)."""
    service = SubtitleService()
    vtt = (
        "WEBVTT\n\n"
        "NOTE\nmulti line\n00:00:00.500 --> 00:00:00.600\nbody\n"
        "1\n00:00:01.000 --> 00:00:02.000\nFirst real\n"
    )
    items = service.parse_subtitles(vtt, "vtt")
    assert items == []
    assert service.last_parse_issues == []


# ================================================================== D4 =====


def test_d4_srt_above_99_hours_parser_and_qa_agree():
    source = "1\n99:59:59,000 --> 100:00:01,000\nvery long media\n"
    service = SubtitleService()
    items = service.parse_subtitles(source, "srt")
    assert len(items) == 1
    report = SubtitleQA().validate(items, "srt", source)
    assert not [f for f in report.findings if f.severity == "error"]


def test_d4_srt_internal_blank_line_parser_and_qa_agree():
    source = "1\n00:00:01,000 --> 00:00:02,000\nline one\n\nline two\n"
    service = SubtitleService()
    items = service.parse_subtitles(source, "srt")
    assert [i.text for i in items] == ["line one\n\nline two"]
    report = SubtitleQA().validate(items, "srt", source)
    assert not [f for f in report.findings if f.severity == "error"]


def test_d4_vtt_single_digit_hour_parser_and_qa_agree():
    source = "WEBVTT\n\n1\n1:00:00.000 --> 1:00:01.000\nlate-night cue\n"
    service = SubtitleService()
    items = service.parse_subtitles(source, "vtt")
    assert len(items) == 1
    report = SubtitleQA().validate(items, "vtt", source)
    assert not [f for f in report.findings if f.severity == "error"]


def test_d4_hourless_vtt_timestamps_still_accepted_by_both_layers():
    source = "WEBVTT\n\n00:00.000 --> 00:01.000\nhello\n"
    service = SubtitleService()
    items = service.parse_subtitles(source, "vtt")
    assert len(items) == 1
    report = SubtitleQA().validate(items, "vtt", source)
    assert not [f for f in report.findings if f.severity == "error"]


@pytest.mark.parametrize(
    "source,file_format",
    [
        ("1\n00:00:02,000 --> 00:00:01,000\nBad time\n", "srt"),
        ("WEBVTT\n\n00:00:60.000 --> 00:01:02.000\nhello\n", "vtt"),
        (
            "[Script Info]\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
            "Effect, Text\n"
            "Dialogue: 0,0:99:01.00,0:00:03.00,Default,,0,0,0,,Hello\n",
            "ass",
        ),
    ],
)
def test_d4_qa_still_rejects_structurally_broken_inputs(source, file_format):
    """D4: unifying the grammar must not excuse genuinely broken input."""
    report = SubtitleQA().validate([], file_format, source)
    assert any(
        f.rule == "invalid_timecode" and f.severity == "error" for f in report.findings
    )


def test_d4_shared_grammar_functions_round_trip_components():
    assert srt_timestamp_to_ms("99:59:59,000") == 99 * 3600000 + 59 * 60000 + 59000
    assert srt_timestamp_to_ms("100:00:01.500") == 3600000 * 100 + 1500
    assert srt_timestamp_to_ms("00:00:60,000") is None
    assert srt_timestamp_to_ms("00:00:01,1234") is None
    assert vtt_timestamp_to_ms("1:00:00.000") == 3600000
    assert vtt_timestamp_to_ms("00:00.5") == 500
    assert vtt_timestamp_to_ms("00:00:60.000") is None
    assert ass_timestamp_to_ms("0:99:01.00") is None
    assert (
        ass_timestamp_to_ms("100:59:59.99") == (100 * 3600 + 59 * 60 + 59) * 1000 + 990
    )
    with pytest.raises(ValueError):
        parse_timestamp_to_ms("00:00:60")


def test_d4_cross_layer_contract_canonical_inputs_produce_no_structural_errors():
    """The parser→QA invariant: what the parser accepts, QA must not contradict."""
    service = SubtitleService()
    canonical = [
        ("1\n00:00:01,000 --> 00:00:02,000\nHello\n", "srt"),
        ("1\n99:59:59,000 --> 100:00:01,000\nLong\n", "srt"),
        ("1\n00:00:01,000 --> 00:00:02,000\nA\n\nB\n", "srt"),
        ("WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\nHello\n", "vtt"),
        ("WEBVTT\n\n1\n1:00:00.000 --> 1:00:01.000\nHello\n", "vtt"),
        ("WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n", "vtt"),
        ("1\n00:00:01,000 --> 00:00:02,000\nHello\n", "txt"),
    ]
    for source, fmt in canonical:
        items = service.parse_subtitles(source, fmt)
        report = SubtitleQA().validate(items, fmt, source)
        structural = [
            f
            for f in report.findings
            if f.severity == "error"
            and f.rule in {"invalid_timecode", "invalid_index", "invalid_format"}
        ]
        assert not structural, (source, fmt, structural)


# ================================================================== D5 =====


def test_d5_safe_detail_keeps_pipeline_config_message():
    from application.api.deps import safe_detail
    from application.services.media_pipeline import PipelineConfigError

    assert (
        safe_detail(PipelineConfigError("output_format debe ser srt o vtt"))
        == "output_format debe ser srt o vtt"
    )
    assert safe_detail(PipelineConfigError("")) == "error interno"


def test_d5_safe_detail_still_sanitizes_other_exceptions():
    from application.api.deps import safe_detail

    assert safe_detail(ValueError("internal path /home/user/secret")) == "error interno"


def test_d5_pipeline_route_returns_useful_422_detail(client):
    response = client.post(
        "/api/v1/pipeline",
        files={"file": ("clip.mp4", b"not-a-video", "video/mp4")},
        data={"output_format": "ass"},
    )
    assert response.status_code == 422
    assert "srt" in response.json()["detail"] and "vtt" in response.json()["detail"]
    assert "Traceback" not in response.text


# ================================================================== D6 =====


def _slow_process_patch(monkeypatch, release):
    """Patch process_subtitles to block until released; returns the call log."""
    from application.services.subtitle_service import (
        ProcessingResult,
        ProcessingStats,
        SubtitleService,
    )

    calls = []

    def slow_process(self, *args, **kwargs):
        calls.append(time.monotonic())
        release.wait(10)
        return ProcessingResult(
            stats=ProcessingStats(processed_items_count=1),
            processed_items=[SubtitleItem(1, 0, 1000, "x")],
            output_content="x",
        )

    monkeypatch.setattr(SubtitleService, "process_subtitles", slow_process)
    return calls


def test_d6_second_start_rejected_while_worker_runs(qapp, tmp_path, monkeypatch):
    """D6: a second _start_processing must not replace the running worker."""
    from application.ui.main_window import MainWindow

    release = threading.Event()
    _slow_process_patch(monkeypatch, release)
    source = tmp_path / "a.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nhola\n", encoding="utf-8")

    window = MainWindow()
    try:
        window.current_subtitle_path = str(source)
        window._start_processing()
        first = window.worker
        assert first is not None and first.isRunning()

        window._start_processing()  # must be a no-op
        assert window.worker is first, "self.worker must not be replaced"
        release.set()
        assert first.wait(15000)
    finally:
        release.set()
        window.deleteLater()


def test_d6_fast_clean_shares_the_reentrancy_guard(qapp, tmp_path, monkeypatch):
    from application.ui.main_window import MainWindow

    release = threading.Event()
    _slow_process_patch(monkeypatch, release)
    source = tmp_path / "b.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nhola\n", encoding="utf-8")

    window = MainWindow()
    try:
        window.current_subtitle_path = str(source)
        window._start_fast_clean()
        first = window.worker
        assert first is not None and first.isRunning()
        window._start_fast_clean()
        assert window.worker is first
        window._start_processing()  # same worker attribute: also guarded
        assert window.worker is first
        release.set()
        assert first.wait(15000)
    finally:
        release.set()
        window.deleteLater()


def test_d6_transcription_second_start_rejected(qapp, tmp_path, monkeypatch):
    from application.services.transcription_service import TranscriptionService
    from application.ui.main_window import MainWindow

    # Whisper may not be installed in the test environment; availability is
    # not what this test exercises.
    monkeypatch.setattr(
        TranscriptionService, "check_available", lambda self, name=None: "whisper"
    )

    release = threading.Event()
    calls = []

    def slow_transcribe(self, *args, **kwargs):
        calls.append(time.monotonic())
        release.wait(10)
        raise RuntimeError("stopped by test")

    monkeypatch.setattr(TranscriptionService, "transcribe_file", slow_transcribe)
    media = tmp_path / "c.mp4"
    media.write_bytes(b"not really a video")

    window = MainWindow()
    try:
        window.current_media_path = str(media)
        window._start_transcription()
        first = window.transcribe_worker
        assert first is not None and first.isRunning()
        window._start_transcription()
        assert window.transcribe_worker is first
        release.set()
        assert first.wait(15000)
    finally:
        release.set()
        window.deleteLater()


# ================================================================== P1 =====


def test_p1_pipeline_result_preserves_parse_issues(tmp_path):
    source = tmp_path / "in.srt"
    source.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\ngood\n\n"
        "2\n00:75:00,000 --> 00:75:01,000\nbad\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.srt"
    config = PipelineConfig(
        input_media=str(source),
        output_subtitle=str(out),
        clean_enabled=False,
        qa_enabled=False,
    ).validate()
    result = MediaPipeline().run(config)
    assert result.success  # advisory, never a failure
    assert len(result.parse_issues) == 1
    issue = result.parse_issues[0]
    assert issue["kind"] == "invalid_timestamp"
    assert issue["line"] == 6
    assert any("parse:" in warning for warning in result.warnings)
    payload = result.to_dict()
    assert payload["parse_issues"] == result.parse_issues


def test_p1_pipeline_history_records_parse_issue_count(tmp_path):
    from application.services.history_store import HistoryStore
    from application.services.media_pipeline import record_pipeline_result

    source = tmp_path / "in.srt"
    source.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\ngood\n\n"
        "2\n00:75:00,000 --> 00:75:01,000\nbad\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.srt"
    config = PipelineConfig(
        input_media=str(source),
        output_subtitle=str(out),
        clean_enabled=False,
        qa_enabled=False,
    ).validate()
    result = MediaPipeline().run(config)
    db = str(tmp_path / "h.db")
    record_pipeline_result(result, config, db)
    with HistoryStore(db) as store:
        row = store.recent_runs(operation="pipeline")[0]
    assert row["parse_issues"] == 1


def test_p1_api_process_result_exposes_parse_issues(client, mock_provider):
    content = (
        "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
        "2\n00:75:00,000 --> 00:75:01,000\nbad block\n"
    )
    response = _upload(client, path="/api/v1/process", content=content)
    assert response.status_code == 202
    job = _wait_job(client, response.json()["job_id"])
    assert job["status"] == "completed"
    issues = job["result"]["parse_issues"]
    assert len(issues) == 1
    assert issues[0]["kind"] == "invalid_timestamp"
    assert job["result"]["stats"]["parse_issues"] == 1


def test_p1_process_stats_model_includes_parse_issues():
    from application.api.schemas import ProcessingMetricsModel

    model = ProcessingMetricsModel(processing_time_seconds=0.1)
    assert model.parse_issues == 0


def test_p1_gui_completion_handler_warns_about_parse_issues(
    qapp, tmp_path, monkeypatch, capsys
):
    """The GUI completion handler must surface parse issues (P1)."""
    from application.services.subtitle_service import (
        ParseIssue,
        ProcessingResult,
        ProcessingStats,
    )
    from application.ui.main_window import MainWindow

    window = MainWindow()
    try:
        source = tmp_path / "d.srt"
        source.write_text("1\n00:00:01,000 --> 00:00:02,000\nhola\n", encoding="utf-8")
        window.current_subtitle_path = str(source)
        window.current_media_path = None
        captured = {}

        class FakeBox:
            @staticmethod
            def warning(_parent, title, desc):
                captured["title"] = title
                captured["desc"] = desc

        monkeypatch.setattr("application.ui.main_window.ThemedMessageBox", FakeBox)
        issue = ParseIssue(
            kind="invalid_timestamp",
            reason="minutos/segundos fuera de rango (00-59): 00:75:00",
            line=6,
            snippet="00:75:00,000 --> 00:75:01,000",
        )
        result = ProcessingResult(
            stats=ProcessingStats(processed_items_count=1),
            original_items=[SubtitleItem(1, 0, 1000, "hola")],
            processed_items=[SubtitleItem(1, 0, 1000, "hola")],
            output_content="1\n00:00:01,000 --> 00:00:02,000\nhola\n",
            parse_issues=[issue],
        )
        window._on_processing_completed(result)
        assert captured.get("title"), "GUI must show a parse-issue warning"
        assert "1" in captured.get("desc", "")
    finally:
        window.deleteLater()


def test_p1_gui_no_warning_when_no_parse_issues(qapp, tmp_path, monkeypatch):
    from application.services.subtitle_service import (
        ProcessingResult,
        ProcessingStats,
    )
    from application.ui.main_window import MainWindow

    window = MainWindow()
    try:
        source = tmp_path / "e.srt"
        source.write_text("1\n00:00:01,000 --> 00:00:02,000\nhola\n", encoding="utf-8")
        window.current_subtitle_path = str(source)
        window.current_media_path = None
        warned = []

        class FakeBox:
            @staticmethod
            def warning(_parent, title, desc):
                warned.append((title, desc))

        monkeypatch.setattr("application.ui.main_window.ThemedMessageBox", FakeBox)
        result = ProcessingResult(
            stats=ProcessingStats(processed_items_count=1),
            original_items=[SubtitleItem(1, 0, 1000, "hola")],
            processed_items=[SubtitleItem(1, 0, 1000, "hola")],
            output_content="1\n00:00:01,000 --> 00:00:02,000\nhola\n",
        )
        window._on_processing_completed(result)
        assert warned == []
    finally:
        window.deleteLater()


def test_p1_parse_issues_are_translated_in_all_catalogs():
    from application.services.i18n_service import I18nService

    catalogs = I18nService.TRANSLATIONS
    for lang, catalog in catalogs.items():
        assert "alert.parse_issues_title" in catalog, lang
        assert "alert.parse_issues_desc" in catalog, lang
        assert "{count}" in catalog["alert.parse_issues_desc"], lang
        assert "{kinds}" in catalog["alert.parse_issues_desc"], lang


def test_p1_gui_history_exposes_parse_issue_column(qapp):
    """The History page shows a parse-issues column instead of dropping it."""
    from application.services.history_store import HistoryStore
    from application.ui.main_window import MainWindow

    window = MainWindow()
    try:
        # The header label is locale-dependent; assert the column exists and
        # carries the recorded count regardless of language.
        assert window.history_table.columnCount() == 8
        with HistoryStore() as store:
            store.record_run("process", file_path="x.srt", parse_issues=3)
        window._refresh_history()
        item = window.history_table.item(0, window.history_table.columnCount() - 1)
        assert item is not None and item.text() == "3"
    finally:
        window.deleteLater()


# ================================================ test-quality upgrades ====


def test_ass_style_test_verifies_real_dialogue_assignment_not_declarations():
    """Replaces the declaration-only assertion with an assignment contract."""
    service = SubtitleService()
    items = service.parse_subtitles(TOP_BOTTOM_DOC, "ass")
    exported = service.format_output(items, "ass")
    assignment = _dialogue_style_fields(exported)
    declared = set()
    for line in exported.splitlines():
        if line.startswith("Style:"):
            declared.add(line.split(":", 1)[1].split(",")[0].strip())
    assert assignment == ["Top", "Bottom"]
    assert set(assignment) <= declared
