from application.services.config_service import ConfigService
from application.services.i18n_service import I18nService
from application.ui.main_window import MainWindow


def test_default_language_is_auto_following_the_system(qapp, tmp_path):
    """Sin configuración guardada, la app sigue el idioma del sistema."""
    config = ConfigService()
    config.config_file = str(tmp_path / "settings.json")
    assert config.get("ui_language", "auto") == "auto"

    service = I18nService(config_service=config)
    assert service.get_configured_language() == "auto"
    assert service.current_language == service.detect_system_language()


def test_saved_language_overrides_the_system_one(qapp, tmp_path):
    """Un idioma elegido antes se respeta aunque el sistema diga otra cosa."""
    config = ConfigService()
    config.config_file = str(tmp_path / "settings.json")
    config.set("ui_language", "it")

    service = I18nService(config_service=config)
    assert service.get_configured_language() == "it"
    assert service.current_language == "it"

    # Volver a "auto" recupera el idioma del sistema y lo guarda
    service.set_language("auto")
    assert service.get_configured_language() == "auto"
    assert service.current_language == service.detect_system_language()


def test_effective_language_label_explains_auto(qapp):
    """La etiqueta aclara si se sigue el sistema o un idioma guardado."""
    win = MainWindow()
    detected_code = win.i18n.detect_system_language()
    detected = win.i18n.SUPPORTED_LANGUAGES[detected_code]["native"]
    other_code = next(c for c in win.i18n.SUPPORTED_LANGUAGES if c != detected_code)
    other = win.i18n.SUPPORTED_LANGUAGES[other_code]["native"]

    win.i18n.set_language("auto")
    win._refresh_effective_language()
    assert detected in win.lbl_lang_effective.text()
    assert detected in win.cb_top_lang.toolTip()

    win.i18n.set_language(other_code)
    win._refresh_effective_language()
    assert other in win.lbl_lang_effective.text()
    assert detected not in win.lbl_lang_effective.text()
    # Fuera del modo automático el tooltip vuelve al texto genérico
    assert win.cb_top_lang.toolTip() == win.i18n.t("topbar.lang_tooltip")


def test_changing_the_combo_refreshes_the_effective_language(qapp):
    win = MainWindow()
    win.cb_settings_lang.setCurrentIndex(win.cb_settings_lang.findData("zh-CN"))
    assert win.i18n.get_configured_language() == "zh-CN"
    assert "简体中文" in win.lbl_lang_effective.text()


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
