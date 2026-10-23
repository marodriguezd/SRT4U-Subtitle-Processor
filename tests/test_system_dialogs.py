"""
Theme regression for system dialogs (QFileDialog / QMessageBox).

These dialogs are top-level and do not inherit the `central_widget` QSS, so
they rely on `Styles.dialog_palette()` + their own QSS. The tests verify the
palette follows the active theme (not the Qt default blue), that toolbar
icons are replaced with themed SVGs and that those icons are
actually visible on the dialog surface.
"""

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox, QSizeGrip, QToolButton

from application.services.i18n_service import get_i18n
from application.ui.file_dialogs import (
    ThemedFileIconProvider,
    _new_dialog,
    prepare_dialog,
)
from application.ui.message_boxes import ThemedMessageBox
from application.ui.styles import Styles

LANGUAGES = ["en", "es", "pt", "de", "it", "fr", "zh-CN"]
TOOLBAR_BUTTONS = [
    "backButton",
    "forwardButton",
    "toParentButton",
    "newFolderButton",
    "listModeButton",
    "detailModeButton",
]
MIN_ICON_CONTRAST = 3.0


def _relative_luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        value = value / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def _contrast(a: QColor, b: QColor) -> float:
    lum_a, lum_b = _relative_luminance(a), _relative_luminance(b)
    high, low = max(lum_a, lum_b), min(lum_a, lum_b)
    return (high + 0.05) / (low + 0.05)


def _icon_contrast(icon, background: QColor, size: int = 16) -> float:
    """Contrast between the icon's most extreme pixel and the dialog background."""
    image = icon.pixmap(size, size).toImage()
    background_lum = _relative_luminance(background)
    best_pixel = None
    best_delta = 0.0
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 40:
                continue
            delta = abs(_relative_luminance(pixel) - background_lum)
            if delta > best_delta:
                best_delta, best_pixel = delta, pixel
    if best_pixel is None:
        return 1.0
    return _contrast(best_pixel, background)


def _make_file_dialog(dark: bool):
    Styles.set_dark(dark)
    dialog = _new_dialog(None, "Open", "", "Videos (*.mp4)")
    dialog.show()
    return dialog


@pytest.mark.parametrize("lang", LANGUAGES)
def test_file_dialog_palette_follows_theme(qapp, lang):
    get_i18n().set_language(lang, save_to_config=False)
    for dark in (True, False):
        dialog = _make_file_dialog(dark)
        try:
            colors = Styles.dialog_colors(dark)
            palette = dialog.palette()
            expected_window = QColor(colors["bg"])
            expected_highlight = QColor(colors["selection"])

            assert palette.window().color().name() == expected_window.name(), (
                f"{lang} (dark={dark}): fondo del diálogo {palette.window().color().name()} "
                f"!= {expected_window.name()}"
            )
            # With an active QSS, QStyleSheetStyle ignores the palette: the
            # selection color must be declared in QSS, never the default blue.
            sheet = dialog.styleSheet()
            assert sheet, "The dialog has no QSS applied"
            assert expected_highlight.name().lower() in sheet.lower(), (
                f"{lang} (dark={dark}): el QSS no declara el color de selección "
                f"{expected_highlight.name()}"
            )
            assert "selection-background-color" in sheet
            assert "selection-color: #ffffff" in sheet.lower()
        finally:
            dialog.close()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_file_dialog_toolbar_icons_are_themed_and_visible(qapp, lang):
    get_i18n().set_language(lang, save_to_config=False)
    for dark in (True, False):
        dialog = _make_file_dialog(dark)
        try:
            background = QColor(Styles.dialog_colors(dark)["bg"])
            buttons = {
                button.objectName(): button
                for button in dialog.findChildren(QToolButton)
                if button.objectName() in TOOLBAR_BUTTONS
            }
            assert buttons, (
                f"{lang}: no se encontraron los botones de la barra de herramientas"
            )
            for name, button in buttons.items():
                assert not button.icon().isNull(), (
                    f"{lang} (dark={dark}): {name} no tiene icono"
                )
                contrast = _icon_contrast(button.icon(), background)
                assert contrast >= MIN_ICON_CONTRAST, (
                    f"{lang} (dark={dark}): el icono de {name} es invisible "
                    f"(contraste {contrast:.2f} < {MIN_ICON_CONTRAST})"
                )
        finally:
            dialog.close()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_file_dialog_uses_themed_icon_provider_and_hides_grip(qapp, lang):
    get_i18n().set_language(lang, save_to_config=False)
    dialog = _make_file_dialog(True)
    try:
        assert isinstance(dialog.iconProvider(), ThemedFileIconProvider), (
            f"{lang}: el diálogo sigue usando los iconos del tema del escritorio"
        )
        assert not [grip for grip in dialog.findChildren(QSizeGrip) if grip.isVisible()]
    finally:
        dialog.close()


def test_prepare_dialog_is_idempotent_and_public(qapp):
    """`prepare_dialog` is the public theming API and can be reapplied."""
    from PyQt6.QtWidgets import QFileDialog

    dialog = QFileDialog(None, "Open", "", "All (*)")
    prepare_dialog(dialog, dark=False)
    prepare_dialog(dialog, dark=False)
    try:
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        assert (
            dialog.palette().window().color().name()
            == QColor(Styles.dialog_colors(False)["bg"]).name()
        )
    finally:
        dialog.close()


def test_message_box_is_themed(qapp):
    for dark in (True, False):
        Styles.set_dark(dark)
        box = ThemedMessageBox.build(
            QMessageBox.Icon.Warning,
            None,
            "Title",
            "Message",
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )
        try:
            assert box.styleSheet(), "The QMessageBox has no QSS applied"
            assert (
                box.palette().window().color().name()
                == QColor(Styles.dialog_colors(dark)["bg"]).name()
            )
            assert box.defaultButton() is not None
        finally:
            box.close()
    Styles.set_dark(True)
