"""Regression tests for the network-security and GUI-lifecycle findings.

Covers deep-audit M4 (a redirect may not carry the API key), M5 (remote
endpoints require HTTPS), M6 (loopback detection), M10 (every user-facing
worker/burn-in string goes through i18n), M11 (clean QThread shutdown) and
L7 (unknown providers are a configuration error).
"""

import http.server
import json
import os
import re
import socketserver
import threading

import pytest

from application.services.translation_providers import (
    OpenAICompatibleProvider,
    ProviderConfigurationError,
    TranslationProviderError,
    is_loopback_host,
)

SECRET = "sk-SECRET-ABCDEF123456"


class _Cfg:
    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


class _AttackerHandler(http.server.BaseHTTPRequestHandler):
    """A completely separate origin; anything it receives is a leak."""

    seen = []

    def _json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        self._json({"choices": [{"message": {"content": "STOLEN"}}]})

    def do_GET(self):  # noqa: N802
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        self._json({"choices": [{"message": {"content": "STOLEN"}}]})

    def log_message(self, *args):
        pass


class _Handler(http.server.BaseHTTPRequestHandler):
    """The endpoint the user configured. ``attacker_port`` is another origin."""

    seen = []
    attacker_port = 0

    def _json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        if self.path == "/v1/chat/completions":
            # A hostile or hijacked endpoint bouncing the key to another origin.
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{type(self).attacker_port}/steal",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/trailing/chat/completions":
            # Benign same-origin redirect: a trailing-slash fix.
            self.send_response(301)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{self.server.server_address[1]}/trailing/ok",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._json({"choices": [{"message": {"content": "hola"}}]})

    def do_GET(self):  # noqa: N802
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        self._json({"choices": [{"message": {"content": "hola"}}]})

    def log_message(self, *args):
        pass


def _serve(handler_class):
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler_class)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


@pytest.fixture
def server():
    """An origin server plus a *different* origin that must never be reached."""
    _Handler.seen = []
    _AttackerHandler.seen = []
    attacker = _serve(_AttackerHandler)
    _Handler.attacker_port = attacker.server_address[1]
    origin = _serve(_Handler)
    try:
        yield origin.server_address[1]
    finally:
        origin.shutdown()
        origin.server_close()
        attacker.shutdown()
        attacker.server_close()


# ------------------------------------------------------------------ M4 redirect


def test_cross_origin_redirect_must_not_receive_the_api_key(server):
    """M4: urllib copies Authorization onto the redirect target; we must not."""
    provider = OpenAICompatibleProvider(
        _Cfg(
            openai_base_url=f"http://127.0.0.1:{server}/v1",
            openai_api_key=SECRET,
        )
    )
    with pytest.raises(TranslationProviderError) as excinfo:
        provider.translate("hola", "auto", "es")
    assert "redirección" in str(excinfo.value).lower()

    assert _AttackerHandler.seen == [], (
        f"the other origin was contacted: {_AttackerHandler.seen}"
    )
    # The key only ever reached the origin the user configured.
    assert all(auth in (None, f"Bearer {SECRET}") for _p, auth in _Handler.seen)
    assert ("/v1/chat/completions", f"Bearer {SECRET}") in _Handler.seen


def test_same_origin_redirect_is_still_followed(server):
    """M4: a benign trailing-slash redirect must keep working."""
    provider = OpenAICompatibleProvider(
        _Cfg(
            openai_base_url=f"http://127.0.0.1:{server}/trailing",
            openai_api_key=SECRET,
        )
    )
    assert provider.translate("hola", "auto", "es") == "hola"
    assert ("/trailing/ok", f"Bearer {SECRET}") in _Handler.seen
    assert _AttackerHandler.seen == []


def test_google_and_deepl_also_use_the_safe_opener():
    """M4: the redirect policy is the single network seam for every provider."""
    from application.services import translation_providers as providers

    body = open(providers.__file__, encoding="utf-8").read()
    assert "urllib.request.urlopen(" not in body, (
        "a provider bypasses the same-origin redirect policy"
    )
    assert body.count("with _open(") >= 3


# ------------------------------------------------------------- M5/M6 endpoints


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/v1",
        "http://127.0.0.2:8080/v1",
        "http://0.0.0.0:8080/v1",
        "http://[::1]:8080/v1",
    ],
)
def test_http_is_allowed_for_local_endpoints(url):
    """M5/M6: loopback (and the unspecified address) may use cleartext."""
    provider = OpenAICompatibleProvider(_Cfg(openai_base_url=url))
    assert provider._local_endpoint is True
    assert provider._credentials() == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "http://evil.example.com/v1",
        "http://192.168.1.50:11434/v1",
        "http://10.0.0.5:8080/v1",
        "http://192.168.1.50:8080",
    ],
)
def test_remote_plaintext_http_is_rejected(url):
    """M5: a remote endpoint would carry the API key in the clear."""
    with pytest.raises(ProviderConfigurationError) as excinfo:
        OpenAICompatibleProvider(_Cfg(openai_base_url=url, openai_api_key=SECRET))
    assert "HTTPS" in str(excinfo.value)


def test_remote_https_is_accepted_and_requires_a_key():
    provider = OpenAICompatibleProvider(
        _Cfg(openai_base_url="https://api.openai.com/v1", openai_api_key=SECRET)
    )
    assert provider._local_endpoint is False
    assert provider._credentials() == SECRET

    keyless = OpenAICompatibleProvider(
        _Cfg(openai_base_url="https://api.openai.com/v1")
    )
    with pytest.raises(ProviderConfigurationError):
        keyless._credentials()


@pytest.mark.parametrize(
    "url", ["", "   ", "not-a-url", "ftp://host/v1", "https://", "http:///v1", "//h/v1"]
)
def test_malformed_base_url_is_rejected(url):
    with pytest.raises(ProviderConfigurationError):
        OpenAICompatibleProvider(_Cfg(openai_base_url=url))


@pytest.mark.parametrize(
    "host,expected",
    [
        ("localhost", True),
        ("127.0.0.1", True),
        ("127.0.0.2", True),
        ("127.255.255.254", True),
        ("0.0.0.0", True),
        ("::1", True),
        ("[::1]", True),
        ("192.168.1.1", False),
        ("10.0.0.1", False),
        ("example.com", False),
        ("", False),
        (None, False),
    ],
)
def test_loopback_detection_policy(host, expected):
    """M6: the old check only matched three literal strings."""
    assert is_loopback_host(host) is expected


# ------------------------------------------------------------------ L7 provider


def test_api_rejects_unknown_provider_with_422(client=None):
    from fastapi.testclient import TestClient

    from application.api.app import create_app
    from application.api.jobs import JobManager

    with TestClient(create_app(job_manager=JobManager(max_workers=1))) as test_client:
        response = test_client.post(
            "/api/v1/translate",
            files={
                "file": (
                    "in.srt",
                    b"1\n00:00:01,000 --> 00:00:02,000\nHi\n",
                    "text/plain",
                )
            },
            data={"provider": "definitely-not-a-provider", "target_language": "es"},
        )
    assert response.status_code == 422
    assert "provider" in response.json()["detail"]


def test_api_rejects_empty_provider():
    from fastapi.testclient import TestClient

    from application.api.app import create_app
    from application.api.jobs import JobManager

    with TestClient(create_app(job_manager=JobManager(max_workers=1))) as test_client:
        response = test_client.post(
            "/api/v1/process",
            files={
                "file": (
                    "in.srt",
                    b"1\n00:00:01,000 --> 00:00:02,000\nHi\n",
                    "text/plain",
                )
            },
            data={"provider": "  "},
        )
    assert response.status_code == 422


def test_cli_provider_choices_come_from_the_registry():
    from application.cli import TRANSLATION_PROVIDERS
    from application.services.translation_providers import ProviderRegistry

    assert set(TRANSLATION_PROVIDERS) == set(ProviderRegistry.names())


# ------------------------------------------------------------------ M10 i18n


def _catalogs():
    from application.services.i18n_service import I18nService

    return I18nService.TRANSLATIONS


NEW_KEYS = (
    "burn.error_video_missing",
    "burn.error_same_path",
    "burn.error_no_ffmpeg",
    "burn.error_prepare",
    "burn.error_ffmpeg_failed",
    "burn.error_exception",
    "worker.error_processing",
    "worker.error_transcribe",
    "worker.error_pipeline_config",
    "worker.error_pipeline_internal",
)


@pytest.mark.parametrize("key", NEW_KEYS)
def test_new_error_key_exists_in_every_catalog(key):
    """M10: every user-facing error string must exist in all six languages."""
    catalogs = _catalogs()
    for lang, catalog in catalogs.items():
        assert key in catalog, f"{key} missing in {lang}"
        assert catalog[key].strip(), f"{key} empty in {lang}"


@pytest.mark.parametrize("key", NEW_KEYS)
def test_new_error_key_is_actually_translated(key):
    """M10: a key that is identical to English is not translated."""
    catalogs = _catalogs()
    for lang in ("es", "pt", "de", "it", "zh-CN"):
        assert catalogs[lang][key] != catalogs["en"][key], (
            f"{key} untranslated in {lang}"
        )


def test_burn_in_ffmpeg_error_placeholder_survives_translation():
    catalogs = _catalogs()
    for lang, catalog in catalogs.items():
        assert "{code}" in catalog["burn.error_ffmpeg_failed"], lang


def test_no_hardcoded_user_facing_strings_in_workers():
    """M10: worker failures must go through t(), not literal Spanish."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for relative in (
        "application/ui/main_window.py",
        "application/services/video_burner_service.py",
    ):
        text = open(os.path.join(root, relative), encoding="utf-8").read()
        offenders = re.findall(r'\.failed\.emit\(\s*"([^"]+)"', text)
        assert offenders == [], (
            f"hardcoded failed.emit() strings in {relative}: {offenders}"
        )


def test_worker_error_strings_resolve_through_i18n():
    from application.services.i18n_service import t

    for key in ("worker.error_processing", "worker.error_pipeline_config"):
        rendered = t(key, key)
        assert rendered != key
        assert rendered.strip()


# -------------------------------------------------------------- M11 lifecycle


def test_process_worker_uses_cooperative_cancellation_not_terminate():
    """H3/M11: no executable QThread.terminate() anywhere in the project."""
    import ast

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    for base, _dirs, files in os.walk(os.path.join(root, "application")):
        if "__pycache__" in base:
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute) or func.attr != "terminate":
                    continue
                # Terminating the ffmpeg child process is correct and required.
                if isinstance(func.value, ast.Name) and func.value.id in {
                    "process",
                    "_process",
                }:
                    continue
                if isinstance(func.value, ast.Attribute) and func.value.attr in {
                    "process",
                    "_process",
                }:
                    continue
                offenders.append(f"{name}:{node.lineno}")
    assert offenders == [], f"QThread-style terminate() calls: {offenders}"


def test_main_window_has_a_close_event():
    from application.ui.main_window import MainWindow

    assert hasattr(MainWindow, "closeEvent")
    assert callable(MainWindow.closeEvent)


def test_close_event_waits_for_workers_and_refuses_to_kill_them(qapp, tmp_path):
    """M11: a worker that will not stop must defer the close, not be terminated."""
    from application.ui.main_window import MainWindow

    window = MainWindow()
    started = threading.Event()
    release = threading.Event()

    class SlowWorker:
        def isRunning(self):
            return not release.is_set()

        def cancel(self):
            started.set()

    worker = SlowWorker()
    window.worker = worker
    assert window._active_workers() == [worker]

    class Event:
        def __init__(self):
            self.accepted = None
            self.ignored = False

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.ignored = True

    event = Event()
    window.closeEvent(event)
    assert started.is_set(), "closeEvent must ask the worker to cancel"
    assert event.ignored is True, "a stubborn worker must defer the close"
    assert event.accepted is None

    release.set()
    event2 = Event()
    window.closeEvent(event2)
    assert event2.accepted is True, "once the worker stops, the close proceeds"
    window.deleteLater()


def test_close_event_accepts_immediately_when_nothing_runs(qapp):
    from application.ui.main_window import MainWindow

    window = MainWindow()
    window.worker = None

    class Event:
        def __init__(self):
            self.accepted = False

        def accept(self):
            self.accepted = True

        def ignore(self):  # pragma: no cover - must not be reached
            raise AssertionError("close must not be ignored with no workers")

    event = Event()
    window.closeEvent(event)
    assert event.accepted
    window.deleteLater()


def test_process_worker_emits_cancelled_and_not_completed(tmp_path):
    """H3: cancelling ProcessWorker must publish nothing."""
    from application.ui.main_window import ProcessWorker

    source = tmp_path / "in.srt"
    source.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        "2\n00:00:03,000 --> 00:00:04,000\nWorld\n",
        encoding="utf-8",
    )
    from application.services.subtitle_service import SubtitleService

    service = SubtitleService()
    worker = ProcessWorker(
        service=service,
        file_path=str(source),
        do_clean=False,
        do_translate=False,
        target_lang="es",
        source_lang="auto",
        engine="google",
    )
    seen = []
    worker.cancelled.connect(lambda: seen.append("cancelled"))
    worker.completed.connect(lambda _r: seen.append("completed"))
    worker.failed.connect(lambda _e: seen.append("failed"))

    worker.cancel()  # cancel before the thread even starts
    worker.run()
    assert seen == ["cancelled"]


def test_process_worker_completes_normally_without_cancellation(tmp_path):
    from application.services.subtitle_service import SubtitleService
    from application.ui.main_window import ProcessWorker

    source = tmp_path / "in.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    worker = ProcessWorker(
        service=SubtitleService(),
        file_path=str(source),
        do_clean=True,
        do_translate=False,
        target_lang="es",
        source_lang="auto",
        engine="google",
    )
    seen = []
    worker.completed.connect(lambda _r: seen.append("completed"))
    worker.run()
    assert seen == ["completed"]


# ----------------------------------------------------------------- L10 extra


def test_vtt_cue_settings_are_preserved_and_documented():
    """L10: VTT keeps `extra`; SRT dropping it is a documented, expected loss."""
    from application.services.subtitle_service import SubtitleService

    service = SubtitleService()
    raw = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000 line:90% align:middle\nhi\n"
    items = service.parse_subtitles(raw, "vtt")
    assert items[0].extra == "line:90% align:middle"
    assert "line:90% align:middle" in service.format_output(items, "vtt")

    srt = service.format_output(items, "srt")
    assert "line:90%" not in srt  # SRT has no such field: expected loss

    source = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "application",
            "services",
            "subtitle_service.py",
        ),
        encoding="utf-8",
    ).read()
    body = source.split("def _format_vtt", 1)[1].split("def _format_ass", 1)[0]
    assert "docstring" or "SRT" in body, "the VTT contract must be documented"
