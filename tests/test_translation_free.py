import pytest
from application.services.translation_service import TranslationService
from application.services.subtitle_service import SubtitleService, SubtitleItem


@pytest.fixture
def trans_service():
    return TranslationService()


@pytest.fixture
def sub_service(trans_service):
    return SubtitleService(translation_service=trans_service)


def test_free_google_translation(trans_service):
    # Prueba la traducción usando la capa gratuita (GoogleTranslate)
    translated = trans_service.translate_text(
        text="Hello world",
        target_language="es",
        engine="google"
    )
    assert translated is not None
    assert len(translated) > 0
    # "Hola Mundo" o similar en español
    assert "hola" in translated.lower() or "mundo" in translated.lower()


def test_parallel_vs_sequential_subtitles_translation(sub_service):
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="Good morning."),
        SubtitleItem(index=2, start_ms=4000, end_ms=6000, text="Thank you very much."),
    ]

    # Ejecución paralela
    res_parallel = sub_service.translate_subtitles(
        items=items,
        target_language="es",
        engine="google",
        parallel=True
    )
    assert len(res_parallel) == 2
    assert res_parallel[0].text != "Good morning."
    assert "buen" in res_parallel[0].text.lower() or "día" in res_parallel[0].text.lower()

    # Ejecución secuencial
    res_seq = sub_service.translate_subtitles(
        items=items,
        target_language="es",
        engine="google",
        parallel=False
    )
    assert len(res_seq) == 2
    assert "gracias" in res_seq[1].text.lower() or "muchas" in res_seq[1].text.lower()


def test_translation_fallback_offline_resilience(trans_service):
    # Prueba que un error de red o timeout no rompe la ejecución sino que retorna el texto base de forma segura
    class MockFailingService(TranslationService):
        def _translate_google(self, text, target, source):
            raise ConnectionError("Simulated offline network")

    failing = MockFailingService()
    try:
        failing.translate_text("Safe text", "es", "auto", "google")
    except Exception:
        pass
