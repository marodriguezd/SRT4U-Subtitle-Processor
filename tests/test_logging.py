"""
Cubre los fallos que antes se silenciaban: registro en el archivo de log,
detección de configuración ilegible/ no escribible y aviso al usuario en la UI.
"""

import json
import logging

import pytest
from PyQt6.QtCore import qCritical, qWarning
from PyQt6.QtWidgets import QMessageBox

from application.logging_setup import (
    get_logger,
    install_qt_message_handler,
    setup_logging,
    uninstall_qt_message_handler,
)
from application.services.config_service import ConfigService
from application.services.i18n_service import get_i18n
from application.services.subtitle_service import (
    ProcessingResult,
    ProcessingStats,
    SubtitleItem,
    SubtitleService,
)
from application.services.translation_service import TranslationService
from application.ui.main_window import MainWindow
from application.ui.message_boxes import ThemedMessageBox


@pytest.fixture(autouse=True)
def _clean_logging():
    """Deja el logger de la app sin handlers al terminar cada test de este módulo."""
    yield
    uninstall_qt_message_handler()
    logger = logging.getLogger("srt4u")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_setup_logging_writes_to_file(tmp_path):
    log_path = setup_logging(config_dir=str(tmp_path), console=False, force=True)
    assert log_path.endswith("srt4u.log")

    get_logger("test").warning("mensaje de prueba")
    for handler in logging.getLogger("srt4u").handlers:
        handler.flush()

    content = (tmp_path / "srt4u.log").read_text(encoding="utf-8")
    assert "mensaje de prueba" in content


def test_setup_logging_survives_unwritable_directory(tmp_path):
    """No poder crear el log no debe impedir que la app arranque."""
    missing = tmp_path / "no" / "existe"
    log_path = setup_logging(config_dir=str(missing), console=False, force=True)

    assert log_path.endswith("srt4u.log")
    get_logger("test").warning("el log no se pudo abrir, pero no se lanza excepción")
    assert not (missing / "srt4u.log").exists()


def test_config_service_reports_save_failure(tmp_path, caplog):
    service = ConfigService()
    service.config_file = str(tmp_path)  # un directorio no se puede abrir como archivo

    caplog.set_level(logging.WARNING, logger="srt4u")
    assert service.set("target_lang", "de") is False
    assert service.save_error
    assert "No se pudo guardar la configuración" in caplog.text


def test_config_service_reports_load_error(tmp_path, caplog):
    service = ConfigService()
    (tmp_path / "settings.json").write_text("{ esto no es json", encoding="utf-8")
    service.config_file = str(tmp_path / "settings.json")

    caplog.set_level(logging.WARNING, logger="srt4u")
    service.load()

    assert service.load_error
    assert service.get("target_lang") == ConfigService.DEFAULT_CONFIG["target_lang"]
    assert "No se pudo leer la configuración" in caplog.text


def test_config_service_saves_valid_json(tmp_path):
    service = ConfigService()
    service.config_file = str(tmp_path / "settings.json")

    assert service.set("openai_model", "gpt-4o") is True
    assert service.save_error is None
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["openai_model"] == "gpt-4o"


def _read_log(tmp_path) -> str:
    for handler in logging.getLogger("srt4u").handlers:
        handler.flush()
    return (tmp_path / "srt4u.log").read_text(encoding="utf-8")


def test_qt_warnings_are_routed_to_the_log(tmp_path):
    """Los avisos de Qt (multimedia, plugins…) deben acabar en el mismo log que la app."""
    setup_logging(config_dir=str(tmp_path), console=False, force=True)
    install_qt_message_handler()

    qWarning("QMediaPlayer: codec unavailable")
    qCritical("QLibraryPrivate: symbol missing")

    content = _read_log(tmp_path)
    assert "QMediaPlayer: codec unavailable" in content
    assert "QLibraryPrivate: symbol missing" in content
    # El nivel se conserva: warning no debe rebajarse a debug ni a error
    warning_line = next(line for line in content.splitlines() if "QMediaPlayer" in line)
    critical_line = next(
        line for line in content.splitlines() if "QLibraryPrivate" in line
    )
    assert "[WARNING] srt4u.qt:" in warning_line
    assert "[ERROR] srt4u.qt:" in critical_line


def test_qt_message_handler_is_idempotent_and_removable(tmp_path):
    setup_logging(config_dir=str(tmp_path), console=False, force=True)
    install_qt_message_handler()
    install_qt_message_handler()  # segunda llamada: no debe duplicar el registro

    qWarning("un solo registro")

    assert _read_log(tmp_path).count("un solo registro") == 1

    uninstall_qt_message_handler()
    uninstall_qt_message_handler()  # no debe fallar si ya se restauró el manejador
    qWarning("mensaje con el manejador por defecto")
    assert "mensaje con el manejador por defecto" not in _read_log(tmp_path)


def test_qt_handler_without_logging_configured_does_not_raise():
    """Sin log configurado, el manejador sigue siendo seguro (no lanza)."""
    logging.getLogger("srt4u").handlers.clear()
    install_qt_message_handler()
    qWarning("aviso sin destino")


def _write_sample_srt(path) -> str:
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nGood morning.\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nThank you very much.\n",
        encoding="utf-8",
    )
    return str(path)


def test_translation_failures_are_counted_and_logged(tmp_path, monkeypatch, caplog):
    def fake_translate(
        self, text, target_language, source_language="auto", engine="google"
    ):
        self._set_last_error("sin conexión con el motor de traducción")
        return text

    monkeypatch.setattr(TranslationService, "translate_text", fake_translate)
    service = SubtitleService()

    items = [
        SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hello"),
        SubtitleItem(index=2, start_ms=1000, end_ms=2000, text="World"),
    ]
    caplog.set_level(logging.WARNING, logger="srt4u")
    service.translate_subtitles(items, target_language="es")
    assert service.last_translation_failures == 2
    assert "no pudo traducir el cue" in caplog.text

    # El contador también llega a las estadísticas del procesamiento completo
    srt_path = _write_sample_srt(tmp_path / "sample.srt")
    result = service.process_subtitles(
        file_path=srt_path,
        do_clean=False,
        do_translate=True,
        target_language="es",
    )
    assert result.stats.translation_failures == 2
    assert "Traducción incompleta" in caplog.text


def test_translation_exceptions_are_logged(tmp_path, monkeypatch, caplog):
    def failing_translate(self, *args, **kwargs):
        raise ConnectionError("motor caído")

    monkeypatch.setattr(TranslationService, "translate_text", failing_translate)
    service = SubtitleService()
    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hello")]

    caplog.set_level(logging.WARNING, logger="srt4u")
    translated = service.translate_subtitles(items, target_language="es")

    assert translated[0].text == "Hello"
    assert service.last_translation_failures == 1
    assert "Excepción al traducir el bloque 1" in caplog.text


def test_main_window_warns_when_translation_fails(qapp, tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(
        ThemedMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: recorded.append(args)),
    )
    window = MainWindow()
    window.current_subtitle_path = _write_sample_srt(tmp_path / "sample.srt")

    items = [SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="Hello")]
    result = ProcessingResult(
        stats=ProcessingStats(total_lines=1, translation_failures=1),
        original_items=items,
        processed_items=items,
        output_content="1\n00:00:01,000 --> 00:00:02,000\nHello\n",
    )
    window._on_processing_completed(result)

    assert recorded, "No se avisó al usuario de la traducción incompleta"
    title, text = recorded[0][1], recorded[0][2]
    assert title == get_i18n().t("alert.translation_failures_title")
    assert "1" in text and "1" in get_i18n().t(
        "alert.translation_failures_desc", failed=1, total=1
    )


def test_settings_save_failure_warns_user(qapp, tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(
        ThemedMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: recorded.append(args)),
    )
    monkeypatch.setattr(
        ThemedMessageBox,
        "information",
        staticmethod(lambda *args, **kwargs: recorded.append(args)),
    )
    window = MainWindow()
    window.config_service.config_file = str(tmp_path)  # escritura imposible

    window._save_settings()

    assert recorded, "No se avisó al usuario del fallo al guardar los ajustes"
    assert recorded[0][1] == get_i18n().t("alert.settings_save_error_title")


def test_message_box_standard_buttons_are_available(qapp):
    """Comprobación de humo del envoltorio tematizado tras añadir el aviso de errores."""
    box = ThemedMessageBox.build(
        QMessageBox.Icon.Critical,
        None,
        "Título",
        "Texto",
        QMessageBox.StandardButton.Ok,
        QMessageBox.StandardButton.Ok,
    )
    try:
        assert box.defaultButton() is not None
    finally:
        box.close()
