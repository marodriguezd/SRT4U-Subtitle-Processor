"""Transcription tests: fake backend only, no real models, no network."""

import json
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from application.api.app import create_app
from application.api.jobs import JobManager
from application.services.history_store import HistoryStore
from application.services.transcription_models import (
    TranscriptionMetrics,
    TranscriptionResult,
    TranscriptionSegment,
)
from application.services.transcription_providers import (
    TranscriptionCancelledError,
    TranscriptionConfig,
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionRegistry,
)
from application.services.transcription_service import TranscriptionService


def _segments():
    return [
        TranscriptionSegment(1, 0, 1500, "hola mundo"),
        TranscriptionSegment(2, 1600, 3200, "esto es una prueba"),
        TranscriptionSegment(3, 3300, 4000, "adiós"),
    ]


class FakeTranscriptionProvider(TranscriptionProvider):
    name = "fake"
    fail_with = None
    seen_configs = []

    def is_available(self) -> bool:
        return True

    def supported_models(self):
        return ["tiny", "small"]

    def transcribe(
        self, media_path, config, *, progress_callback=None, cancel_event=None
    ):
        FakeTranscriptionProvider.seen_configs.append(config)
        if FakeTranscriptionProvider.fail_with is not None:
            raise FakeTranscriptionProvider.fail_with
        if cancel_event is not None and cancel_event.is_set():
            raise TranscriptionCancelledError("transcripción cancelada")
        segments = _segments()
        for position, segment in enumerate(segments, 1):
            if progress_callback is not None:
                progress_callback(
                    "transcribing", {"segments": position, "end_ms": segment.end_ms}
                )
        metrics = TranscriptionMetrics.build(
            provider=self.name,
            model=config.model,
            source_language=config.normalized_language() or "auto",
            segments=segments,
            media_duration_ms=4000,
            processing_duration_ms=2000,
        )
        return TranscriptionResult(
            segments=segments,
            language=config.normalized_language() or "auto",
            duration_ms=4000,
            model=config.model,
            provider=self.name,
            processing_time_ms=2000,
            success=True,
            metrics=metrics,
            metadata={"device": "cpu"},
        )


@pytest.fixture
def fake_registry(monkeypatch):
    monkeypatch.setattr(
        TranscriptionRegistry,
        "get",
        lambda name, config_service=None: FakeTranscriptionProvider(),
    )
    FakeTranscriptionProvider.fail_with = None
    FakeTranscriptionProvider.seen_configs = []


@pytest.fixture
def media_file(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00\x01fakemedia")
    return str(path)


@pytest.fixture
def api_client():
    app = create_app(job_manager=JobManager(max_workers=2))
    with TestClient(app) as test_client:
        yield test_client


# -- registry & abstraction -------------------------------------------------


def test_registry_has_whisper_and_rejects_unknown():
    assert "whisper" in TranscriptionRegistry.names()
    with pytest.raises(TranscriptionError):
        TranscriptionRegistry.get("no-existe")
    with pytest.raises(TranscriptionError):
        TranscriptionRegistry.get("  ")
    with pytest.raises(ValueError):
        TranscriptionRegistry.register("whisper", lambda **kwargs: None)


def test_whisper_provider_unavailable_without_backend():
    try:
        import faster_whisper  # noqa: F401

        pytest.skip("faster-whisper installed; availability covered elsewhere")
    except ImportError:
        pass
    provider = TranscriptionRegistry.get("whisper")
    assert provider.is_available() is False
    assert "small" in provider.supported_models()
    with pytest.raises(TranscriptionError) as exc_info:
        provider.transcribe("x.mp4", TranscriptionConfig())
    assert exc_info.value.error_type == "provider_not_installed"


def test_config_language_normalization():
    assert TranscriptionConfig(language="auto").normalized_language() is None
    assert TranscriptionConfig(language="").normalized_language() is None
    assert TranscriptionConfig(language="ES").normalized_language() == "es"
    assert TranscriptionConfig(language=" es ").normalized_language() == "es"


# -- models & metrics --------------------------------------------------------


def test_metrics_realtime_factor_only_when_known():
    segments = _segments()
    full = TranscriptionMetrics.build(
        provider="fake",
        model="tiny",
        source_language="es",
        segments=segments,
        media_duration_ms=4000,
        processing_duration_ms=2000,
    )
    assert full.real_time_factor == 0.5
    assert full.segment_count == 3
    assert full.words_output == 7
    unknown = TranscriptionMetrics.build(
        provider="fake",
        model="tiny",
        source_language="es",
        segments=segments,
        media_duration_ms=None,
        processing_duration_ms=2000,
    )
    assert unknown.real_time_factor is None
    zero = TranscriptionMetrics.build(
        provider="fake",
        model="tiny",
        source_language="es",
        segments=segments,
        media_duration_ms=0,
        processing_duration_ms=2000,
    )
    assert zero.real_time_factor is None


def test_result_serialization_is_json_safe():
    result = TranscriptionResult(
        segments=_segments(),
        language="es",
        duration_ms=4000,
        model="tiny",
        processing_time_ms=2000,
        metrics=TranscriptionMetrics.build(
            provider="fake",
            model="tiny",
            source_language="es",
            segments=_segments(),
            media_duration_ms=4000,
            processing_duration_ms=2000,
        ),
    )
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["language"] == "es"
    assert payload["metrics"]["real_time_factor"] == 0.5
    assert len(payload["segments"]) == 3
    assert payload["segments"][0]["start_ms"] == 0


def test_segments_to_subtitle_items_validates():
    result = TranscriptionResult(
        segments=[
            TranscriptionSegment(7, 0, 1500, "  hola  "),
            TranscriptionSegment(8, 1600, 1600, "fija fin"),
            TranscriptionSegment(9, 2000, 2500, "   "),
            TranscriptionSegment(10, -500, 500, "clamp inicio"),
        ],
        language="es",
    )
    items = result.to_subtitle_items()
    assert [item.index for item in items] == [1, 2, 3]
    assert items[0].text == "hola"
    assert items[1].end_ms > items[1].start_ms
    assert items[2].start_ms == 0


# -- service: validation, rendering ------------------------------------------


def test_service_rejects_missing_and_unsupported(media_file):
    service = TranscriptionService()
    with pytest.raises(TranscriptionError) as exc_info:
        service.transcribe_file("/no/existe.mp4")
    assert exc_info.value.error_type == "invalid_file"
    bad = media_file.replace(".mp4", ".xyz")
    with open(media_file, "rb") as source, open(bad, "wb") as target:
        target.write(source.read())
    with pytest.raises(TranscriptionError) as exc_info:
        service.transcribe_file(bad)
    assert exc_info.value.error_type == "unsupported_format"


def test_service_transcribe_and_render_srt_vtt(fake_registry, media_file):
    service = TranscriptionService()
    result = service.transcribe_file(media_file, model="tiny", language="es")
    assert result.success
    assert result.language == "es"
    assert len(result.segments) == 3
    srt = service.render(result, "srt")
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "hola mundo" in srt
    vtt = service.render(result, "vtt")
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.500" in vtt
    with pytest.raises(TranscriptionError):
        service.render(result, "ass")


def test_service_forwards_progress_and_cancel(fake_registry, media_file):
    service = TranscriptionService()
    events = []
    result = service.transcribe_file(
        media_file, progress_callback=lambda step, payload: events.append(step)
    )
    assert result.success
    assert events == ["transcribing"] * 3
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(TranscriptionError) as exc_info:
        service.transcribe_file(media_file, cancel_event=cancelled)
    assert exc_info.value.error_type == "cancelled"


def test_check_available_reports_missing_backend():
    service = TranscriptionService()
    try:
        import faster_whisper  # noqa: F401

        pytest.skip("backend installed here")
    except ImportError:
        pass
    with pytest.raises(TranscriptionError):
        service.check_available("whisper")


# -- analytics / QA reuse ------------------------------------------------------


def test_transcription_feeds_analytics_and_qa(fake_registry, media_file):
    service = TranscriptionService()
    result = service.transcribe_file(media_file, language="es")
    items = service.to_subtitle_items(result)
    analytics, qa_report = service.subtitle_service.analyze_subtitles(
        items, file_format="srt", source_content=service.render(result, "srt")
    )
    assert analytics.content.subtitle_count == 3
    assert analytics.timing.total_duration_ms == 4000
    assert qa_report.error_count == 0
    report_only = service.subtitle_service.qa_subtitles(items, file_format="srt")
    assert report_only.passed


# -- history -------------------------------------------------------------------


def test_history_records_transcription_without_texts(
    fake_registry, media_file, tmp_path
):
    service = TranscriptionService()
    result = service.transcribe_file(media_file, language="es")
    db = str(tmp_path / "history.db")
    with HistoryStore(db) as store:
        run_id = store.record_transcription_result(
            result, file_path=media_file, file_format="srt"
        )
        rows = store.recent_runs(operation="transcription")
    assert run_id > 0
    row = rows[0]
    assert row["provider"] == "fake"
    assert row["model"] == "small"
    assert row["source_language"] == "es"
    assert row["number_of_cues"] == 3
    assert row["media_duration_ms"] == 4000
    assert row["duration_ms"] == 2000
    assert row["success"] == 1
    blob = json.dumps(rows)
    assert "hola mundo" not in blob


# -- CLI -------------------------------------------------------------------------


def test_cli_transcribe_with_fake(
    fake_registry, media_file, tmp_path, monkeypatch, capsys
):
    from application import cli

    db = str(tmp_path / "history.db")
    out = str(tmp_path / "out.srt")
    code = cli.main(
        [
            "transcribe",
            media_file,
            "-o",
            out,
            "--model",
            "tiny",
            "--language",
            "es",
            "--db",
            db,
        ]
    )
    assert code == 0
    content = open(out, encoding="utf-8").read()
    assert "hola mundo" in content
    printed = capsys.readouterr()
    assert "3 cues" in printed.out
    with HistoryStore(db) as store:
        rows = store.recent_runs(operation="transcription")
    assert len(rows) == 1
    assert rows[0]["file_format"] == "srt"


def test_cli_transcribe_stats_json(fake_registry, media_file, tmp_path, capsys):
    from application import cli

    out = str(tmp_path / "out.vtt")
    code = cli.main(
        [
            "transcribe",
            media_file,
            "-o",
            out,
            "--format",
            "vtt",
            "--stats-json",
            "--no-history",
        ]
    )
    assert code == 0
    assert open(out, encoding="utf-8").read().startswith("WEBVTT")
    printed = capsys.readouterr()
    metrics = json.loads(printed.out.strip().splitlines()[-1])
    assert metrics["segment_count"] == 3
    assert metrics["real_time_factor"] == 0.5


def test_cli_transcribe_missing_backend(media_file, capsys):
    try:
        import faster_whisper  # noqa: F401

        pytest.skip("backend installed here")
    except ImportError:
        pass
    from application import cli

    code = cli.main(["transcribe", media_file, "--no-history"])
    assert code == 2
    assert "transcription" in capsys.readouterr().err.lower()


def test_cli_transcribe_bad_extension(tmp_path, fake_registry, capsys):
    from application import cli

    bad = tmp_path / "doc.txt"
    bad.write_text("no es multimedia", encoding="utf-8")
    code = cli.main(["transcribe", str(bad), "--no-history"])
    assert code == 2


# -- API ---------------------------------------------------------------------------


def _wait_job(client, job_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise TimeoutError(job_id)


def test_api_transcribe_job_lifecycle(fake_registry, api_client):
    response = api_client.post(
        "/api/v1/transcribe",
        files={"file": ("clip.mp4", b"\x00fakemedia", "video/mp4")},
        data={"model": "tiny", "language": "es", "output_format": "srt"},
    )
    assert response.status_code == 202
    job = _wait_job(api_client, response.json()["job_id"])
    assert job["operation"] == "transcription"
    assert job["status"] == "completed"
    assert "hola mundo" in job["result"]["output_content"]
    assert job["result"]["language"] == "es"
    assert job["result"]["metrics"]["segment_count"] == 3


def test_api_transcribe_validation(api_client):
    response = api_client.post(
        "/api/v1/transcribe",
        files={"file": ("clip.mp4", b"x", "video/mp4")},
        data={"model": "bogus"},
    )
    assert response.status_code == 422
    response = api_client.post(
        "/api/v1/transcribe",
        files={"file": ("clip.srt", b"x", "text/plain")},
        data={"model": "tiny"},
    )
    assert response.status_code == 400
    response = api_client.post(
        "/api/v1/transcribe",
        files={"file": ("clip.mp4", b"x", "video/mp4")},
        data={"model": "tiny", "output_format": "ass"},
    )
    assert response.status_code == 422


def test_api_transcribe_missing_backend_reports_safely(api_client):
    try:
        import faster_whisper  # noqa: F401

        pytest.skip("backend installed here")
    except ImportError:
        pass
    response = api_client.post(
        "/api/v1/transcribe",
        files={"file": ("clip.mp4", b"\x00fakemedia", "video/mp4")},
        data={"model": "tiny"},
    )
    assert response.status_code == 202
    job = _wait_job(api_client, response.json()["job_id"])
    assert job["status"] == "failed"
    assert "Traceback" not in (job["error"] or "")
    assert "transcription" in (job["error"] or "").lower()


def test_api_transcribe_openapi_lists_route(api_client):
    spec = api_client.get("/openapi.json").json()
    assert "/api/v1/transcribe" in spec["paths"]


# -- GUI -----------------------------------------------------------------------------


def test_transcribe_page_wired(qapp):
    from application.ui.main_window import MainWindow

    win = MainWindow()
    assert win.stack.count() == 11
    win._switch_page(9)
    assert win.stack.currentIndex() == 9
    assert win.cb_transcribe_model.currentText() == "small"
    assert win.le_transcribe_lang.text() == "auto"
    try:
        import faster_whisper  # noqa: F401

        assert win.btn_start_transcribe.isEnabled()
    except ImportError:
        assert not win.btn_start_transcribe.isEnabled()
        assert "transcription" in win.lbl_transcribe_avail.text().lower()
    win._choose_transcribe_file = lambda: None
    win.current_media_path = "/no/existe.mp4"
    media_filter = win._transcribe_media_filter()
    assert "*.mp4" in media_filter and ";;" in media_filter
    assert media_filter.endswith(win.i18n.t("dialog.all_files"))


# -- jobs ----------------------------------------------------------------------------


def test_job_cancel_marks_cancelled():
    manager = JobManager(max_workers=1)
    started = threading.Event()
    release = threading.Event()

    def _slow():
        started.set()
        release.wait(timeout=10)
        return {}

    first = manager.submit("transcription", _slow)
    assert started.wait(timeout=5)
    second = manager.submit("transcription", _slow)
    assert manager.cancel(second) == "cancelled"
    release.set()
    job = manager.wait_for(first, timeout=10)
    assert job["status"] == "completed"
    assert manager.get(second)["status"] == "cancelled"
    manager.shutdown()


# -- full fake integration ---------------------------------------------------------------


def test_fake_transcription_end_to_end(fake_registry, media_file, tmp_path):
    service = TranscriptionService()
    result = service.transcribe_file(media_file, language="es")
    items = service.to_subtitle_items(result)
    content = service.render(result, "srt")
    analytics, qa_report = service.subtitle_service.analyze_subtitles(
        items, file_format="srt", source_content=content
    )
    db = str(tmp_path / "history.db")
    with HistoryStore(db) as store:
        run_id = store.record_transcription_result(
            result, file_path=media_file, file_format="srt"
        )
        assert store.get_run(run_id)["operation"] == "transcription"
    assert analytics.content.subtitle_count == len(items) == 3
    assert qa_report.passed or qa_report.error_count == 0
    assert "adiós" in content
    assert os.environ.get("SRT4U_TRANSCRIPTION_PROVIDER", "whisper") == "whisper"
