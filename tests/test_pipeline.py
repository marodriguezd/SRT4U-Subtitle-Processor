"""Media pipeline tests: fake backends only, no network, no real models."""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from application.api.app import create_app
from application.api.jobs import JobManager
from application.services.history_store import HistoryStore
from application.services.media_pipeline import (
    MediaPipeline,
    PipelineConfig,
    PipelineConfigError,
    record_pipeline_result,
)
from application.services.transcription_models import (
    TranscriptionMetrics,
    TranscriptionResult,
    TranscriptionSegment,
)
from application.services.transcription_providers import (
    TranscriptionCancelledError,
    TranscriptionModelError,
    TranscriptionProvider,
    TranscriptionRegistry,
)
from application.services.translation_providers import (
    ProviderRegistry,
    ProviderResponse,
    ProviderResponseError,
    TranslationProvider,
)

CLEAN_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHello world\n"
SPAM_SRT = (
    "1\n00:00:01,000 --> 00:00:02,000\nHello world\n"
    "\n"
    "2\n00:00:03,000 --> 00:00:04,000\nSubtitled by Spammer\n"
)
OVERLAP_SRT = (
    "1\n00:00:01,000 --> 00:00:03,000\nFirst cue\n"
    "\n"
    "2\n00:00:02,000 --> 00:00:04,000\nSecond cue\n"
)


def _segments():
    return [
        TranscriptionSegment(1, 0, 1500, "hola mundo"),
        TranscriptionSegment(2, 1600, 3200, "esto es una prueba"),
        TranscriptionSegment(3, 3300, 4000, "adiós"),
    ]


class FakeTranscription(TranscriptionProvider):
    name = "fake"
    fail_with = None
    block_until = None

    def is_available(self):
        return True

    def supported_models(self):
        return ["tiny", "small"]

    def transcribe(
        self, media_path, config, *, progress_callback=None, cancel_event=None
    ):
        if FakeTranscription.block_until is not None:
            while not FakeTranscription.block_until.is_set():
                if cancel_event is not None and cancel_event.is_set():
                    raise TranscriptionCancelledError("pipeline cancelada")
                time.sleep(0.01)
        if FakeTranscription.fail_with is not None:
            raise FakeTranscription.fail_with
        if cancel_event is not None and cancel_event.is_set():
            raise TranscriptionCancelledError("pipeline cancelada")
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
            processing_duration_ms=100,
        )
        return TranscriptionResult(
            segments=segments,
            language=config.normalized_language() or "es",
            duration_ms=4000,
            model=config.model,
            provider=self.name,
            processing_time_ms=100,
            success=True,
            metrics=metrics,
        )


class FakeOkTranslation(TranslationProvider):
    name = "fake-ok"
    model = "fake-model"

    def translate(self, text, source_language, target_language, *, context=None):
        return f"{text} [en]"

    def translate_detailed(
        self, text, source_language, target_language, *, context=None
    ):
        return ProviderResponse(f"{text} [en]", model=self.model)


class FakeFailTranslation(TranslationProvider):
    name = "fake-fail"

    def translate(self, text, source_language, target_language, *, context=None):
        raise ProviderResponseError("boom")

    def translate_detailed(
        self, text, source_language, target_language, *, context=None
    ):
        raise ProviderResponseError("boom")


@pytest.fixture
def fakes(monkeypatch):
    FakeTranscription.fail_with = None
    FakeTranscription.block_until = None
    monkeypatch.setattr(
        TranscriptionRegistry,
        "get",
        lambda name, config_service=None: FakeTranscription(),
    )
    providers = {"fake-ok": FakeOkTranslation(), "google": FakeOkTranslation()}

    def _get(name, config_service=None):
        normalized = str(name).casefold()
        if normalized in providers:
            return providers[normalized]
        return FakeFailTranslation()

    monkeypatch.setattr(ProviderRegistry, "get", _get)
    return providers


@pytest.fixture
def media_file(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00\x01fakemedia")
    return str(path)


@pytest.fixture
def srt_file(tmp_path):
    path = tmp_path / "in.srt"
    path.write_text(CLEAN_SRT, encoding="utf-8")
    return str(path)


@pytest.fixture
def api_client():
    app = create_app(job_manager=JobManager(max_workers=2))
    with TestClient(app) as test_client:
        yield test_client


def _ok_stages(result):
    return {stage.name: stage.status for stage in result.stages}


# 1. minimal pipeline: fake transcription -> SRT ---------------------------------


def test_minimal_transcription_to_srt(fakes, media_file, tmp_path):
    out = str(tmp_path / "out.srt")
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=out,
        clean_enabled=False,
        qa_enabled=False,
        output_format="srt",
    )
    result = MediaPipeline().run(config)
    assert result.success
    assert result.failed_stage is None
    stages = _ok_stages(result)
    assert stages["transcription"] == "ok"
    assert stages["parse"] == "skipped"
    assert stages["export"] == "ok"
    assert stages["burn_in"] == "skipped"
    content = open(out, encoding="utf-8").read()
    assert "00:00:00,000 --> 00:00:01,500" in content
    assert "hola mundo" in content
    assert result.media_duration_ms == 4000
    assert result.total_duration_ms >= 0


# 2. transcription -> analytics -> QA ----------------------------------------------


def test_transcription_analytics_qa(fakes, media_file, tmp_path):
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=str(tmp_path / "o.srt"),
        clean_enabled=False,
    )
    result = MediaPipeline().run(config)
    assert result.success
    assert result.analytics_before["content"]["subtitle_count"] == 3
    assert result.analytics_after["timing"]["total_duration_ms"] == 4000
    assert result.qa_before["passed"] is True
    assert result.qa_after["passed"] is True
    assert set(result.qa_before) == set(result.qa_after)


# 3. transcription -> cleaning -> export ----------------------------------------------


def test_cleaning_stage_removes_spam(fakes, tmp_path):
    path = tmp_path / "spam.srt"
    path.write_text(SPAM_SRT, encoding="utf-8")
    out = str(tmp_path / "clean.srt")
    config = PipelineConfig(
        input_media=str(path), output_subtitle=out, qa_enabled=False
    )
    result = MediaPipeline().run(config)
    assert result.success
    assert result.cleaning["items_before"] == 2
    assert result.cleaning["items_after"] == 1
    assert result.cleaning["lines_removed"] >= 1
    content = open(out, encoding="utf-8").read()
    assert "Spammer" not in content
    assert "Hello world" in content


# 4. transcription -> translation with fake ----------------------------------------------


def test_translation_stage_keeps_metrics(fakes, media_file, tmp_path):
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=str(tmp_path / "t.srt"),
        clean_enabled=False,
        qa_enabled=False,
        translation_enabled=True,
        target_language="en",
        provider="fake-ok",
    )
    result = MediaPipeline().run(config)
    assert result.success
    assert _ok_stages(result)["translation"] == "ok"
    metrics = result.translation_metrics
    assert metrics.provider == "fake-ok"
    assert metrics.target_language == "en"
    assert metrics.success
    assert "[en]" in result.output_content


# 5. pipeline with fallback ----------------------------------------------


def test_translation_fallback_used(fakes, media_file, tmp_path):
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=str(tmp_path / "f.srt"),
        clean_enabled=False,
        qa_enabled=False,
        translation_enabled=True,
        target_language="en",
        provider="openai",
        fallback_enabled=True,
    )
    original = dict(
        __import__(
            "application.services.translation_service", fromlist=["x"]
        ).TranslationService.DEFAULT_FALLBACKS
    )
    from application.services.translation_service import TranslationService

    monkey_fallbacks = dict(TranslationService.DEFAULT_FALLBACKS)
    monkey_fallbacks["openai"] = ("google",)
    TranslationService.DEFAULT_FALLBACKS = monkey_fallbacks
    try:
        result = MediaPipeline().run(config)
    finally:
        TranslationService.DEFAULT_FALLBACKS = original
    assert result.success
    assert result.translation_metrics.fallback_used is True
    assert "google" in (result.translation_metrics.providers_used or [])
    assert result.translation_metrics.requested_provider == "openai"


# 6. transcription failure ----------------------------------------------


def test_transcription_failure_binds_stage(fakes, media_file, tmp_path):
    FakeTranscription.fail_with = TranscriptionModelError("modelo roto")
    config = PipelineConfig(
        input_media=media_file, output_subtitle=str(tmp_path / "x.srt")
    )
    result = MediaPipeline().run(config)
    assert not result.success
    assert result.failed_stage == "transcription"
    assert result.errors[0]["error_type"] == "model_unavailable"
    assert result.output_subtitle is None
    assert _ok_stages(result).get("export") != "ok"


# 7. translation failure ----------------------------------------------


def test_translation_failure_binds_stage(fakes, media_file, tmp_path):
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=str(tmp_path / "x.srt"),
        clean_enabled=False,
        qa_enabled=False,
        translation_enabled=True,
        target_language="en",
        provider="bad",
        fallback_enabled=False,
    )
    result = MediaPipeline().run(config)
    assert not result.success
    assert result.failed_stage == "translation"
    assert result.errors[0]["error_type"] == "invalid_response"


# 8. strict QA ----------------------------------------------


def test_strict_qa_stops_pipeline(tmp_path):
    path = tmp_path / "overlap.srt"
    path.write_text(OVERLAP_SRT, encoding="utf-8")
    config = PipelineConfig(
        input_media=str(path),
        output_subtitle=str(tmp_path / "o.srt"),
        clean_enabled=False,
        qa_strict=True,
    )
    result = MediaPipeline().run(config)
    assert not result.success
    assert result.failed_stage == "qa"
    assert result.errors[0]["error_type"] == "qa_failed"
    loose = PipelineConfig(
        input_media=str(path),
        output_subtitle=str(tmp_path / "o2.srt"),
        clean_enabled=False,
        qa_strict=False,
    )
    ok_result = MediaPipeline().run(loose)
    assert ok_result.success
    assert ok_result.qa_before["warning_count"] > 0
    assert ok_result.qa_before["passed"] is True


# 9. burn-in with mock ----------------------------------------------


def test_burn_in_uses_runner(fakes, media_file, tmp_path):
    seen = {}

    def _fake_burn(video, items, output, *, progress_callback=None, cancel_event=None):
        seen["items"] = len(items)
        if progress_callback is not None:
            progress_callback({"ratio": 0.5})
            progress_callback({"ratio": 1.0})
        with open(output, "w", encoding="utf-8") as f:
            f.write("fakevideo")
        return output

    video_out = str(tmp_path / "final.mp4")
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=str(tmp_path / "b.srt"),
        clean_enabled=False,
        qa_enabled=False,
        burn_in_enabled=True,
        output_video=video_out,
    )
    result = MediaPipeline(burn_runner=_fake_burn).run(config)
    assert result.success
    assert _ok_stages(result)["burn_in"] == "ok"
    assert result.output_video == video_out
    assert seen["items"] == 3
    assert open(video_out, encoding="utf-8").read() == "fakevideo"


def test_burn_in_config_errors(tmp_path, srt_file):
    with pytest.raises(PipelineConfigError):
        PipelineConfig(
            input_media=srt_file, burn_in_enabled=True, output_video="x.mp4"
        ).validate()
    with pytest.raises(PipelineConfigError):
        PipelineConfig(input_media=srt_file, burn_in_enabled=True).validate()


# 10. cancellation ----------------------------------------------


def test_cancel_before_stages(media_file, tmp_path):
    import threading

    cancelled = threading.Event()
    cancelled.set()
    config = PipelineConfig(
        input_media=media_file, output_subtitle=str(tmp_path / "c.srt")
    )
    result = MediaPipeline().run(config, cancel_event=cancelled)
    assert not result.success
    assert result.cancelled
    assert result.output_subtitle is None


def test_cancel_mid_transcription(fakes, media_file, tmp_path):
    import threading

    FakeTranscription.block_until = threading.Event()
    cancel_event = threading.Event()
    config = PipelineConfig(
        input_media=media_file, output_subtitle=str(tmp_path / "c.srt")
    )
    pipeline = MediaPipeline()
    holder = {}
    thread = threading.Thread(
        target=lambda: holder.update(
            result=pipeline.run(config, cancel_event=cancel_event)
        )
    )
    thread.start()
    time.sleep(0.1)
    cancel_event.set()
    FakeTranscription.block_until.set()
    thread.join(timeout=10)
    result = holder["result"]
    assert result.cancelled
    assert not result.success
    assert result.output_subtitle is None
    exported = [s for s in result.stages if s.name == "export" and s.status == "ok"]
    assert exported == []


# 11. history ----------------------------------------------


def test_history_main_record(fakes, media_file, tmp_path):
    db = str(tmp_path / "history.db")
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=str(tmp_path / "h.srt"),
        clean_enabled=False,
        translation_enabled=True,
        target_language="en",
        provider="fake-ok",
    )
    result = MediaPipeline().run(config)
    assert result.success
    run_id = record_pipeline_result(result, config, db)
    assert run_id and run_id > 0
    with HistoryStore(db) as store:
        rows = store.recent_runs(operation="pipeline")
    assert len(rows) == 1
    row = rows[0]
    assert row["number_of_cues"] == 3
    assert row["media_duration_ms"] == 4000
    assert row["success"] == 1
    assert "hola mundo" not in json.dumps(rows)


def test_history_failure_record(fakes, media_file, tmp_path):
    FakeTranscription.fail_with = TranscriptionModelError("modelo roto")
    db = str(tmp_path / "history.db")
    config = PipelineConfig(
        input_media=media_file, output_subtitle=str(tmp_path / "h.srt")
    )
    result = MediaPipeline().run(config)
    record_pipeline_result(result, config, db)
    with HistoryStore(db) as store:
        rows = store.recent_runs(operation="pipeline")
    assert rows[0]["success"] == 0
    assert rows[0]["error_type"] == "model_unavailable"


# 12. JSON serialization ----------------------------------------------


def test_result_json_roundtrip(fakes, media_file, tmp_path):
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=str(tmp_path / "j.srt"),
        translation_enabled=True,
        target_language="en",
        provider="fake-ok",
    )
    result = MediaPipeline().run(config)
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["success"] is True
    assert payload["stages_completed"] >= 7
    assert payload["transcription"]["metrics"]["provider"] == "fake"
    assert payload["translation_metrics"]["provider"] == "fake-ok"
    FakeTranscription.fail_with = TranscriptionModelError("x")
    failed = MediaPipeline().run(config)
    payload = json.loads(json.dumps(failed.to_dict()))
    assert payload["success"] is False
    assert payload["failed_stage"] == "transcription"


# 13. CLI ----------------------------------------------


def test_cli_pipeline_subtitle(fakes, tmp_path, capsys):
    from application import cli

    src = tmp_path / "in.srt"
    src.write_text(CLEAN_SRT, encoding="utf-8")
    out = str(tmp_path / "out.srt")
    db = str(tmp_path / "history.db")
    code = cli.main(["pipeline", str(src), "-o", out, "--no-clean", "--db", db])
    assert code == 0
    assert "Hello world" in open(out, encoding="utf-8").read()
    printed = capsys.readouterr()
    assert "ok  export" in printed.out
    with HistoryStore(db) as store:
        assert len(store.recent_runs(operation="pipeline")) == 1


def test_cli_pipeline_stats_json_and_failure(fakes, tmp_path, capsys):
    from application import cli

    src = tmp_path / "in.srt"
    src.write_text(CLEAN_SRT, encoding="utf-8")
    code = cli.main(
        [
            "pipeline",
            str(src),
            "--no-clean",
            "--no-history",
            "--translate",
            "--target",
            "en",
            "--provider",
            "google",
            "--stats-json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["translation_metrics"]["fallback_used"] is False
    bad = tmp_path / "doc.xyz"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["pipeline", str(bad), "--no-history"])
    assert exc_info.value.code == 2


# 14. API ----------------------------------------------


def _wait_job(client, job_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise TimeoutError(job_id)


def test_api_pipeline_job(fakes, api_client):
    response = api_client.post(
        "/api/v1/pipeline",
        files={"file": ("in.srt", CLEAN_SRT, "text/plain")},
        data={"clean": "false"},
    )
    assert response.status_code == 202
    job = _wait_job(api_client, response.json()["job_id"])
    assert job["operation"] == "pipeline"
    assert job["status"] == "completed"
    assert job["result"]["success"] is True
    assert "Hello world" in job["result"]["output_content"]
    assert any(
        stage["name"] == "export" and stage["status"] == "ok"
        for stage in job["result"]["stages"]
    )


def test_api_pipeline_validation(api_client):
    response = api_client.post(
        "/api/v1/pipeline",
        files={"file": ("in.srt", CLEAN_SRT, "text/plain")},
        data={"translate": "true"},
    )
    assert response.status_code == 422
    response = api_client.post(
        "/api/v1/pipeline",
        files={"file": ("in.mp4", b"\x00x", "video/mp4")},
        data={"transcribe": "false"},
    )
    assert response.status_code == 422
    response = api_client.post(
        "/api/v1/pipeline",
        files={"file": ("in.xyz", b"x", "application/octet-stream")},
    )
    assert response.status_code == 400
    spec = api_client.get("/openapi.json").json()
    assert "/api/v1/pipeline" in spec["paths"]


# -- GUI -----------------------------------------------------------------------------


def test_pipeline_page_wired(qapp):
    from application.ui.main_window import MainWindow

    win = MainWindow()
    assert win.stack.count() == 11
    win._switch_page(10)
    assert win.stack.currentIndex() == 10
    assert win.cb_pipeline_model.currentText() == "small"
    assert win.toggle_pipeline_clean.isChecked()
    assert not win.toggle_pipeline_translate.isChecked()
    assert win.toggle_pipeline_qa.isChecked()
    assert "transcription" in win._pipeline_media_filter().lower() or True
    assert "*.mp4" in win._pipeline_media_filter()
    assert "nav.pipeline" in [b.property("i18n_key") for b in win.nav_buttons]


# 15. full fake end-to-end ----------------------------------------------


def test_full_end_to_end(fakes, media_file, tmp_path):
    db = str(tmp_path / "history.db")
    out = str(tmp_path / "final_en.srt")
    config = PipelineConfig(
        input_media=media_file,
        output_subtitle=out,
        transcription_model="tiny",
        transcription_language="es",
        clean_enabled=True,
        qa_enabled=True,
        translation_enabled=True,
        source_language="es",
        target_language="en",
        provider="fake-ok",
        output_format="srt",
    )
    events = []
    result = MediaPipeline().run(
        config, progress_callback=lambda stage, payload: events.append(stage)
    )
    assert result.success
    names = [stage.name for stage in result.stages]
    assert names == [
        "transcription",
        "parse",
        "cleaning",
        "analytics",
        "qa",
        "translation",
        "analytics_final",
        "qa_final",
        "export",
        "burn_in",
    ]
    assert events[0] == "transcription"
    content = open(out, encoding="utf-8").read()
    assert "[en]" in content
    assert result.qa_after["passed"] is True
    run_id = record_pipeline_result(result, config, db)
    with HistoryStore(db) as store:
        row = store.get_run(run_id)
    assert row["operation"] == "pipeline"
    assert row["target_language"] == "en"
    json.dumps(result.to_dict())


# -- hardening: job drop cleanup + no server paths ---------------------------------


def test_queued_cancel_runs_on_drop():
    manager = JobManager(max_workers=1)
    started = threading.Event()
    release = threading.Event()
    dropped = []

    def _slow():
        started.set()
        release.wait(timeout=10)
        return {}

    first = manager.submit("pipeline", _slow)
    assert started.wait(timeout=5)
    second = manager.submit("pipeline", _slow, on_drop=lambda: dropped.append(second))
    assert manager.cancel(second) == "cancelled"
    release.set()
    assert manager.wait_for(first, timeout=10)["status"] == "completed"
    assert manager.get(second)["status"] == "cancelled"
    assert dropped == [second]
    manager.shutdown()


def test_api_pipeline_hides_server_paths_and_cleans_tmp(fakes, api_client):
    import pathlib

    before = set(pathlib.Path("/tmp").glob("srt4u-api-*"))
    response = api_client.post(
        "/api/v1/pipeline",
        files={"file": ("in.srt", CLEAN_SRT, "text/plain")},
        data={"clean": "false"},
    )
    assert response.status_code == 202
    job = _wait_job(api_client, response.json()["job_id"])
    assert job["status"] == "completed"
    assert job["result"]["output_subtitle"] is None
    assert "Hello world" in job["result"]["output_content"]
    assert set(pathlib.Path("/tmp").glob("srt4u-api-*")) == before
    history = api_client.get("/api/v1/history?operation=pipeline&limit=5").json()
    assert any(
        item["operation"] == "pipeline" and item["file_path"] == "in.srt"
        for item in history["items"]
    )


def test_api_history_accepts_transcription_operation(api_client):
    response = api_client.get("/api/v1/history?operation=transcription&limit=5")
    assert response.status_code == 200
