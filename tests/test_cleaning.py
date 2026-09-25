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

    # El bloque 1 era completamente spam (Subtitled by AnimeFansubPro + t.me link) -> eliminado
    assert not any("AnimeFansubPro" in it.text for it in cleaned)
    assert not any("t.me" in it.text for it in cleaned)
    # Bloque 3 era solo música ♪ -> eliminado
    assert not any("♪" in it.text for it in cleaned)
    # Bloque 4 tenía spam de www.subtitlesfree.org pero diálogo válido
    item_scene = [it for it in cleaned if "fingerprints on the window" in it.text]
    assert len(item_scene) == 1
    assert "subtitlesfree.org" not in item_scene[0].text

    # Verifica que se conservan las etiquetas de estilo
    assert any("<i>Good morning" in it.text for it in cleaned)
    assert any("<b>We need to hurry</b>" in it.text for it in cleaned)

    assert deleted_lines >= 4
    assert len(cleaned) < len(items)


def test_clean_vtt_spam_removal(service):
    path = os.path.join(FIXTURES_DIR, "sample.vtt")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "vtt")
    cleaned, total_lines, deleted_lines = service.clean_subtitles(items)

    assert not any("YTS.MX" in it.text for it in cleaned)
    assert not any("t.me/tech_news" in it.text for it in cleaned)
    # Mantiene diálogo real
    assert any("Welcome to the conference" in it.text for it in cleaned)
    assert any("machine learning is here" in it.text for it in cleaned)
    assert deleted_lines >= 2


def test_clean_ass_spam_removal(service):
    path = os.path.join(FIXTURES_DIR, "sample.ass")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    items = service.parse_subtitles(content, "ass")
    cleaned, total_lines, deleted_lines = service.clean_subtitles(items)

    # Bloque 1 era spam de FansubZone
    assert not any("FansubZone" in it.text for it in cleaned)
    assert any("mountains in the distance" in it.text for it in cleaned)
    assert any(r"{\an8}" in it.text for it in cleaned)
    assert deleted_lines >= 1
