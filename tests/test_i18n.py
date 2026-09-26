import os
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

QMessageBox.information = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.critical = lambda *args, **kwargs: QMessageBox.StandardButton.Ok

from application.services.i18n_service import I18nService, t, get_i18n
from application.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_i18n_service_translations():
    service = I18nService()
    languages = ["en", "es", "pt", "de", "it", "zh-CN"]
    for lang in languages:
        assert lang in service.supported_languages

    # Check key translations across languages
    service.set_language("en")
    assert service.t("nav.home") == "Home"
    assert service.t("nav.about") == "About"

    service.set_language("es")
    assert service.t("nav.home") == "Inicio"
    assert service.t("nav.about") == "Acerca de"

    service.set_language("pt")
    assert service.t("nav.home") == "Início"
    assert service.t("nav.about") == "Sobre"

    service.set_language("de")
    assert service.t("nav.home") == "Startseite"
    assert service.t("nav.about") == "Über"

    service.set_language("it")
    assert service.t("nav.home") == "Home"
    assert service.t("nav.about") == "Informazioni"

    service.set_language("zh-CN")
    assert service.t("nav.home") == "首页"
    assert service.t("nav.about") == "关于"


def test_i18n_fallback():
    service = I18nService()
    service.set_language("zh-CN")
    # Non-existent key should return fallback default or key itself
    val = service.t("non.existent.key", default="Default Val")
    assert val == "Default Val"

    val_no_def = service.t("another.non.existent.key")
    assert val_no_def == "another.non.existent.key"


def test_main_window_i18n_switching(qapp):
    win = MainWindow()

    # Default UI language test
    assert win.i18n is not None

    # Switch to English
    win.cb_top_lang.setCurrentIndex(win.cb_top_lang.findData("en"))
    assert win.i18n.current_language == "en"
    assert win.nav_buttons[0].text().strip() == "Home"
    assert not win.nav_buttons[0].icon().isNull()
    assert win.btn_fast_clean.text().strip() == "Clean File Now"
    assert not win.btn_fast_clean.icon().isNull()

    # Verify settings combo is synchronized
    assert win.cb_settings_lang.currentData() == "en"

    # Switch to Spanish via settings combo
    win.cb_settings_lang.setCurrentIndex(win.cb_settings_lang.findData("es"))
    assert win.i18n.current_language == "es"
    assert win.nav_buttons[0].text().strip() == "Inicio"
    assert not win.nav_buttons[0].icon().isNull()
    assert win.btn_fast_clean.text().strip() == "Limpiar archivo ahora"
    assert not win.btn_fast_clean.icon().isNull()
    assert win.cb_top_lang.currentData() == "es"

    # Switch to German
    win.cb_top_lang.setCurrentIndex(win.cb_top_lang.findData("de"))
    assert win.i18n.current_language == "de"
    assert win.nav_buttons[0].text().strip() == "Startseite"
    assert not win.nav_buttons[0].icon().isNull()
    assert win.btn_fast_clean.text().strip() == "Datei jetzt bereinigen"
    assert not win.btn_fast_clean.icon().isNull()

    # Switch to Chinese
    win.cb_top_lang.setCurrentIndex(win.cb_top_lang.findData("zh-CN"))
    assert win.i18n.current_language == "zh-CN"
    assert win.nav_buttons[0].text().strip() == "首页"
    assert not win.nav_buttons[0].icon().isNull()
    assert win.btn_fast_clean.text().strip() == "立即清理文件"
    assert not win.btn_fast_clean.icon().isNull()
