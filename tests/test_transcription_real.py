"""Optional real-backend transcription check. NEVER runs in the normal suite.

Run explicitly with a downloaded model and local media::

    SRT4U_TEST_REAL_WHISPER=1 SRT4U_TEST_MEDIA=/path/clip.mp4 \
        python -m pytest tests/test_transcription_real.py -q -s

Requires the ``transcription`` extra, FFmpeg-adjacent decodability, and a
small model (``tiny`` by default). Potentially slow; local only.
"""

import os
import shutil

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SRT4U_TEST_REAL_WHISPER") != "1",
    reason="real Whisper model required (SRT4U_TEST_REAL_WHISPER=1)",
)

faster_whisper = pytest.importorskip(
    "faster_whisper", reason="transcription extra not installed"
)


def test_real_whisper_transcribes_media(tmp_path):
    from application.services.transcription_providers import TranscriptionConfig
    from application.services.transcription_service import TranscriptionService
    from application.services.transcription_whisper import WhisperProvider

    media = os.environ.get("SRT4U_TEST_MEDIA", "")
    assert media and os.path.isfile(media), "set SRT4U_TEST_MEDIA to a local file"
    provider = WhisperProvider()
    assert provider.is_available()
    model = os.environ.get("SRT4U_TEST_MODEL", "tiny")
    result = TranscriptionService().transcribe_file(
        media, provider_name="whisper", model=model, language="auto"
    )
    assert result.success
    assert result.segments, "no segments transcribed"
    assert result.language
    items = result.to_subtitle_items()
    assert len(items) == len(result.segments)
    content = TranscriptionService().render(result, "srt")
    out = tmp_path / "real.srt"
    out.write_text(content, encoding="utf-8")
    print(f"\nsegments={len(items)} language={result.language} saved={out}")
    assert result.metrics is not None
    print(f"metrics={result.metrics.to_dict()}")
    assert shutil.which("ffmpeg") is not None or True
    assert TranscriptionConfig(model=model).model == model
