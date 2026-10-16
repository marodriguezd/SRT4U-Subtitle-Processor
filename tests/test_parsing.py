import os
import pytest
from application.services.subtitle_service import (
    SubtitleService,
    ms_to_srt_time,
    ms_to_vtt_time,
    ms_to_ass_time,
    parse_timestamp_to_ms,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def service():
    return SubtitleService()


def test_timestamp_conversions():
    # 01:23:45.678 -> 5025678 ms
    ms = (1 * 3600 + 23 * 60 + 45) * 1000 + 678
    assert parse_timestamp_to_ms("01:23:45,678") == ms
    assert parse_timestamp_to_ms("01:23:45.678") == ms
    assert ms_to_srt_time(ms) == "01:23:45,678"
    assert ms_to_vtt_time(ms) == "01:23:45.678"
    assert ms_to_ass_time(ms) == "1:23:45.68"


def test_detect_format_by_extension(service):
    assert service.detect_format("", "movie.srt") == "srt"
    assert service.detect_format("", "movie.vtt") == "vtt"
    assert service.detect_format("", "movie.ass") == "ass"
    assert service.detect_format("", "movie.ssa") == "ass"
    assert service.detect_format("", "movie.txt") == "txt"


def test_detect_format_by_content(service):
    assert service.detect_format("WEBVTT\n00:00.000 --> 00:01.000\nHi") == "vtt"
    assert service.detect_format("[Script Info]\nTitle: Test\n[Events]") == "ass"
    assert service.detect_format("1\n00:00:01,000 --> 00:00:02,000\nHello") == "srt"
    assert service.detect_format("Just plain text without timestamps.") == "txt"


def test_parse_srt_fixture(service):
    path = os.path.join(FIXTURES_DIR, "sample.srt")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "srt")
    assert len(items) == 5
    assert items[0].index == 1
    assert items[0].start_ms == 1200
    assert items[0].end_ms == 4500
    assert "Subtitled by AnimeFansubPro" in items[0].text
    assert "fingerprints on the window" in items[3].text


def test_parse_vtt_fixture(service):
    path = os.path.join(FIXTURES_DIR, "sample.vtt")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "vtt")
    assert len(items) == 4
    assert items[0].start_ms == 2100
    assert items[0].end_ms == 5300
    assert "artificial intelligence" in items[1].text


def test_parse_ass_fixture(service):
    path = os.path.join(FIXTURES_DIR, "sample.ass")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "ass")
    assert len(items) == 4
    assert items[1].style == "Default"
    assert "mountains in the distance" in items[1].text
    assert items[2].style == "TopStyle"
    assert "reach the camp" in items[2].text


def test_parse_txt_fixture(service):
    path = os.path.join(FIXTURES_DIR, "sample.txt")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "txt")
    assert len(items) == 4
    assert "welcome to the show" in items[0].text
    assert items[1].start_ms > items[0].start_ms


def test_parse_vtt_metadata_vs_identifier(service):
    content = """WEBVTT

NOTE This is a valid comment
That spans multiple lines

NOTED
00:00:01.000 --> 00:00:02.000
Valid cue with NOTED id

REGIONAL
00:00:03.000 --> 00:00:04.000
Valid cue with REGIONAL id
"""
    items = service.parse_subtitles(content, "vtt")
    assert len(items) == 2
    assert "Valid cue with NOTED id" in items[0].text
    assert "Valid cue with REGIONAL id" in items[1].text


def test_parse_vtt_adjacent_cues_without_blank_lines(service):
    content = """WEBVTT

00:00:01.000 --> 00:00:02.000
Line 1
00:00:03.000 --> 00:00:04.000
Line 2
"""
    items = service.parse_subtitles(content, "vtt")
    assert len(items) == 2
    assert items[0].text == "Line 1"
    assert items[1].text == "Line 2"


def test_negative_timestamp_clamping():
    assert ms_to_srt_time(-500) == "00:00:00,000"
    assert ms_to_vtt_time(-1000) == "00:00:00.000"


def test_read_subtitle_file_encodings(tmp_path):
    from application.services.subtitle_service import read_subtitle_file

    p_bom = tmp_path / "bom.srt"
    p_bom.write_bytes(b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    assert "Hello" in read_subtitle_file(str(p_bom))

    p_u16 = tmp_path / "u16.srt"
    p_u16.write_bytes(
        b"\xff\xfe" + "1\n00:00:01,000 --> 00:00:02,000\nUtf16\n".encode("utf-16-le")
    )
    assert "Utf16" in read_subtitle_file(str(p_u16))
