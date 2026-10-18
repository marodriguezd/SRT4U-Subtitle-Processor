import os
import pytest
from application.services.subtitle_service import SubtitleService

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def service():
    return SubtitleService()


def test_clean_srt_spam_removal(service):
    path = os.path.join(FIXTURES_DIR, "sample.srt")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "srt")
    cleaned, total_lines, deleted_lines = service.clean_subtitles(items)

    # Cue 1 was pure spam (Subtitled by AnimeFansubPro + t.me link) -> removed
    assert not any("AnimeFansubPro" in it.text for it in cleaned)
    assert not any("t.me" in it.text for it in cleaned)
    # Cue 3 was music-only ♪ -> removed
    assert not any("♪" in it.text for it in cleaned)
    # Cue 4 carried www.subtitlesfree.org spam alongside valid dialogue
    item_scene = [it for it in cleaned if "fingerprints on the window" in it.text]
    assert len(item_scene) == 1
    assert "subtitlesfree.org" not in item_scene[0].text

    # Style tags are preserved
    assert any("<i>Good morning" in it.text for it in cleaned)
    assert any("<b>We need to hurry</b>" in it.text for it in cleaned)

    assert deleted_lines >= 4
    assert len(cleaned) < len(items)


def test_combined_spam_matcher_is_equivalent_to_per_pattern_checks(service):
    """M-4: the single alternation must return the historical verdict.

    The optimisation is only safe if ``is_spam_line`` still answers exactly
    like ``any(fullmatch)`` over the whole-line list plus ``any(search)`` over
    the promotional/advertising lists, for both spam and real dialogue.
    """
    corpus = [
        "Subtitled by AnimeFansubPro",
        "SUBTITULADO POR ALGUIEN",
        "Subtítulos sincronizados por alguien",
        "Traducción de alguien",
        "www.city.com",
        "https://example.org/path",
        "t.me/channel",
        "telegram: @channel",
        "YTS.MX",
        "rarbg",
        "opensubtitles.org",
        "♪",
        "♪ music ♪",
        "[music]",
        "(music playing)",
        "We compress knowledge for you!",
        "Visit us at www.site.org for more.",
        "Please download from t.me/x",
        "Watch this free online HD movie now",
        "Your free subtitles are available on our site",
        "Donate to our project",
        "Rate this movie on IMDb",
        "I went to www.city.com yesterday.",
        "The rarbg group released it.",
        "I downloaded it from opensubtitles.",
        "Hello, how are you?",
        "Señor, ¿qué pasa?",
        "♪ La la la ♪",
        "",
        "   ",
    ]
    for line in corpus:
        expected = (
            any(p.fullmatch(line.strip()) for p in service.spam_patterns)
            or any(p.search(line.strip()) for p in service.promotional_patterns)
            or any(p.search(line.strip()) for p in service.advertisement_patterns)
        )
        assert service.is_spam_line(line) is expected, line


def test_clean_vtt_spam_removal(service):
    path = os.path.join(FIXTURES_DIR, "sample.vtt")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "vtt")
    cleaned, total_lines, deleted_lines = service.clean_subtitles(items)

    assert not any("YTS.MX" in it.text for it in cleaned)
    assert not any("t.me/tech_news" in it.text for it in cleaned)
    # Real dialogue is kept
    assert any("Welcome to the conference" in it.text for it in cleaned)
    assert any("machine learning is here" in it.text for it in cleaned)
    assert deleted_lines >= 2


def test_clean_ass_spam_removal(service):
    path = os.path.join(FIXTURES_DIR, "sample.ass")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "ass")
    cleaned, total_lines, deleted_lines = service.clean_subtitles(items)

    # Cue 1 was FansubZone spam
    assert not any("FansubZone" in it.text for it in cleaned)
    assert any("mountains in the distance" in it.text for it in cleaned)
    assert any(r"{\an8}" in it.text for it in cleaned)
    assert deleted_lines >= 1
