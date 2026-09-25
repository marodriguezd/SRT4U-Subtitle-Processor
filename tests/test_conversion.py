import os
import pytest
from application.services.subtitle_service import SubtitleService

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def service():
    return SubtitleService()


def test_srt_to_all_formats(service):
    path = os.path.join(FIXTURES_DIR, "sample.srt")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "srt")

    # 1. SRT -> VTT
    vtt = service.format_output(items, "vtt")
    assert vtt.startswith("WEBVTT")
    vtt_items = service.parse_subtitles(vtt, "vtt")
    assert len(vtt_items) == len(items)

    # 2. SRT -> ASS
    ass = service.format_output(items, "ass")
    assert "[Script Info]" in ass
    assert "Dialogue:" in ass
    ass_items = service.parse_subtitles(ass, "ass")
    assert len(ass_items) == len(items)

    # 3. SRT -> TXT
    txt = service.format_output(items, "txt")
    assert "Good morning, detective" in txt
    txt_items = service.parse_subtitles(txt, "txt")
    assert len(txt_items) >= 4


def test_ass_to_srt(service):
    path = os.path.join(FIXTURES_DIR, "sample.ass")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    ass_items = service.parse_subtitles(content, "ass")
    srt_out = service.format_output(ass_items, "srt")

    assert "-->" in srt_out
    srt_items = service.parse_subtitles(srt_out, "srt")
    assert len(srt_items) == len(ass_items)


def test_vtt_to_srt(service):
    path = os.path.join(FIXTURES_DIR, "sample.vtt")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    vtt_items = service.parse_subtitles(content, "vtt")
    srt_out = service.format_output(vtt_items, "srt")

    assert "-->" in srt_out
    srt_items = service.parse_subtitles(srt_out, "srt")
    assert len(srt_items) == len(vtt_items)
