"""Deterministic tests for the Whisper provider's init, fallback and cancellation.

A fake ``WhisperModel`` is injected through ``_load_faster_whisper`` so no
real model is downloaded and no GPU is touched. These tests verify the mocked
control flow only; real inference and real CUDA behaviour are not covered here.
"""

import sys
import threading
import types

import pytest

from application.services import transcription_whisper as tw
from application.services.transcription_providers import (
    TranscriptionCancelledError,
    TranscriptionConfig,
    TranscriptionError,
    TranscriptionMemoryError,
    TranscriptionModelError,
    TranscriptionNotInstalledError,
    TranscriptionUnknownError,
)


class _Segment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


class _Info:
    language = "en"
    duration = 4.0


class _FakeWhisperFactory:
    """Records constructor calls; ``fail_on`` maps device -> exception to raise."""

    def __init__(self, fail_on=None, segments=None, infer_error=None, after=None):
        self.fail_on = fail_on or {}
        self.segments = (
            segments
            if segments is not None
            else [
                _Segment(0.0, 1.0, "hello"),
                _Segment(1.0, 2.0, "world"),
            ]
        )
        self.infer_error = infer_error
        self.after = after  # callback run between yielded segments
        self.calls = []

    def __call__(self, model, **kwargs):
        self.calls.append((model, kwargs))
        device = kwargs.get("device")
        if device in self.fail_on:
            raise self.fail_on[device]
        factory = self

        class _Model:
            def transcribe(self, media_path, **options):
                def gen():
                    for index, seg in enumerate(factory.segments):
                        if factory.after is not None:
                            factory.after(index)
                        yield seg
                    if factory.infer_error is not None:
                        raise factory.infer_error

                return gen(), _Info()

        return _Model()


@pytest.fixture
def media_file(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"not really media; the fake model never decodes it")
    return str(path)


@pytest.fixture
def install_fake(monkeypatch):
    def _install(factory):
        monkeypatch.setattr(tw, "_load_faster_whisper", lambda: factory)
        return factory

    return _install


def _config(device="auto", model="tiny"):
    return TranscriptionConfig(model=model, device=device)


def test_missing_faster_whisper_raises_install_hint(monkeypatch, media_file):
    monkeypatch.setattr(tw, "_load_faster_whisper", lambda: None)
    provider = tw.WhisperProvider()
    assert provider.is_available() is False
    with pytest.raises(TranscriptionNotInstalledError) as info:
        provider.transcribe(media_file, _config())
    assert "python -m pip install" in str(info.value)


def test_auto_device_falls_back_to_cpu_when_cuda_init_fails(
    install_fake, media_file, monkeypatch
):
    monkeypatch.setattr(
        tw.WhisperProvider, "_resolve_device", staticmethod(lambda d: "cuda")
    )
    factory = install_fake(
        _FakeWhisperFactory(fail_on={"cuda": RuntimeError("CUDA driver not found")})
    )

    result = tw.WhisperProvider().transcribe(media_file, _config("auto"))

    assert [c[1]["device"] for c in factory.calls] == ["cuda", "cpu"]
    assert factory.calls[0][1]["compute_type"] == "float16"
    assert factory.calls[1][1]["compute_type"] == "int8"
    assert result.success is True
    assert result.metadata["device"] == "cpu"
    assert [s.text for s in result.segments] == ["hello", "world"]


def test_auto_device_cpu_fallback_failure_is_normalized_and_chained(
    install_fake, media_file, monkeypatch
):
    monkeypatch.setattr(
        tw.WhisperProvider, "_resolve_device", staticmethod(lambda d: "cuda")
    )
    cpu_error = RuntimeError("cpu allocator broke")
    factory = install_fake(
        _FakeWhisperFactory(
            fail_on={"cuda": RuntimeError("CUDA init"), "cpu": cpu_error}
        )
    )

    with pytest.raises(TranscriptionUnknownError) as info:
        tw.WhisperProvider().transcribe(media_file, _config("auto"))

    assert len(factory.calls) == 2
    assert info.value.__cause__ is cpu_error
    # Only the exception type is exposed; the raw message may contain paths or secrets.
    assert "cpu allocator broke" not in str(info.value)
    assert "RuntimeError" in str(info.value)


def test_explicit_cuda_does_not_fall_back_to_cpu(install_fake, media_file):
    cuda_error = RuntimeError("CUDA init")
    factory = install_fake(_FakeWhisperFactory(fail_on={"cuda": cuda_error}))

    with pytest.raises(TranscriptionUnknownError) as info:
        tw.WhisperProvider().transcribe(media_file, _config("cuda"))

    assert [c[1]["device"] for c in factory.calls] == ["cuda"]
    assert info.value.__cause__ is cuda_error


def test_cpu_model_init_failure_is_not_retried(install_fake, media_file):
    factory = install_fake(
        _FakeWhisperFactory(fail_on={"cpu": RuntimeError("model file is corrupt")})
    )

    with pytest.raises(TranscriptionUnknownError):
        tw.WhisperProvider().transcribe(media_file, _config("cpu"))

    assert len(factory.calls) == 1


def test_unsupported_device_is_rejected_before_model_init(install_fake, media_file):
    factory = install_fake(_FakeWhisperFactory())

    with pytest.raises(TranscriptionError, match="unsupported device"):
        tw.WhisperProvider().transcribe(media_file, _config("tpu"))

    assert factory.calls == []


def test_unknown_model_is_rejected_before_model_init(install_fake, media_file):
    factory = install_fake(_FakeWhisperFactory())

    with pytest.raises(TranscriptionModelError) as info:
        tw.WhisperProvider().transcribe(media_file, _config("cpu", model="huge"))

    assert factory.calls == []
    assert "supported:" in str(info.value)


def test_cuda_inference_failure_is_not_retried_on_cpu(
    install_fake, media_file, monkeypatch
):
    """Inference-time CUDA errors are reported, not retried: fallback covers init only."""
    monkeypatch.setattr(
        tw.WhisperProvider, "_resolve_device", staticmethod(lambda d: "cuda")
    )
    factory = install_fake(
        _FakeWhisperFactory(
            segments=[],
            infer_error=RuntimeError("CUDA error: an illegal memory access"),
        )
    )

    with pytest.raises(TranscriptionMemoryError):
        tw.WhisperProvider().transcribe(media_file, _config("auto"))

    assert [c[1]["device"] for c in factory.calls] == ["cuda"]


def test_failure_after_partial_segments_discards_work_and_raises(
    install_fake, media_file
):
    install_fake(
        _FakeWhisperFactory(
            segments=[_Segment(0.0, 1.0, "partial")],
            infer_error=RuntimeError("decoder crashed mid-stream"),
        )
    )

    with pytest.raises(TranscriptionUnknownError):
        tw.WhisperProvider().transcribe(media_file, _config("cpu"))


def test_cancel_before_start_skips_model_init(install_fake, media_file):
    factory = install_fake(_FakeWhisperFactory())
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(TranscriptionCancelledError):
        tw.WhisperProvider().transcribe(media_file, _config("cpu"), cancel_event=cancel)

    assert factory.calls == []


def test_cancel_during_iteration_stops_and_releases_partial_result(
    install_fake, media_file
):
    cancel = threading.Event()
    install_fake(
        _FakeWhisperFactory(
            segments=[
                _Segment(0.0, 1.0, "a"),
                _Segment(1.0, 2.0, "b"),
                _Segment(2.0, 3.0, "c"),
            ],
            after=lambda index: cancel.set() if index == 1 else None,
        )
    )

    with pytest.raises(TranscriptionCancelledError):
        tw.WhisperProvider().transcribe(media_file, _config("cpu"), cancel_event=cancel)


def test_secrets_in_backend_message_are_not_exposed(install_fake, media_file):
    secret = "sk-test-SECRET-1234567890"
    install_fake(
        _FakeWhisperFactory(fail_on={"cpu": RuntimeError(f"auth header {secret}")})
    )

    with pytest.raises(TranscriptionError) as info:
        tw.WhisperProvider().transcribe(media_file, _config("cpu"))

    assert secret not in str(info.value)
    assert secret in repr(
        info.value.__cause__
    )  # diagnostic context is kept on the chain


def test_auto_resolves_to_cpu_without_cuda_devices(monkeypatch):
    monkeypatch.setattr(tw, "_load_faster_whisper", lambda: object())
    fake = types.ModuleType("ctranslate2")
    fake.get_cuda_device_count = lambda: 0
    monkeypatch.setitem(sys.modules, "ctranslate2", fake)

    assert tw.WhisperProvider._resolve_device("auto") == "cpu"


def test_auto_resolves_to_cuda_when_device_present(monkeypatch):
    monkeypatch.setattr(tw, "_load_faster_whisper", lambda: object())
    fake = types.ModuleType("ctranslate2")
    fake.get_cuda_device_count = lambda: 1
    monkeypatch.setitem(sys.modules, "ctranslate2", fake)

    assert tw.WhisperProvider._resolve_device("auto") == "cuda"
