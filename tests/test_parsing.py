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
    assert ms_to_ass_time(ms) == "1:23:45.67"


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
