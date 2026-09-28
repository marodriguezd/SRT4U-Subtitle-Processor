"""
Contraste de la barra lateral en ambos temas.

La pestaña activa se pintaba con `color: #C7D2FE` fijo (un lavanda claro pensado
para el fondo oscuro) sobre un tinte translúcido de PRIMARY. En el tema claro el
texto quedaba en ~1.1:1, ilegible, y los iconos del menú (calibrados para el
fondo oscuro) se quedaban por debajo de 3:1.

Los tests compositional el fondo real — la barra lateral es translúcida y la
pestaña activa encima — y exigen WCAG AA en los dos temas.
"""

import re

import pytest
from PyQt6.QtGui import QColor

from application.ui.icons import Icons
from application.ui.main_window import MainWindow
from application.ui.styles import Styles

# Colores de fondo bajo la barra lateral en cada tema (de `BG_*_GRADIENT`).
UNDER_LIGHT = QColor("#F8FAFC")
UNDER_DARK = QColor("#0F1426")
MIN_TEXT_CONTRAST = 4.5
MIN_ICON_CONTRAST = 3.0


def _luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        value = value / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def _contrast(a: QColor, b: QColor) -> float:
    lum_a, lum_b = _luminance(a), _luminance(b)
    return (max(lum_a, lum_b) + 0.05) / (min(lum_a, lum_b) + 0.05)


def _blend(top: QColor, alpha: float, bottom: QColor) -> QColor:
    return QColor(
        *(
            round(top.red() * alpha + bottom.red() * (1 - alpha)),
            round(top.green() * alpha + bottom.green() * (1 - alpha)),
            round(top.blue() * alpha + bottom.blue() * (1 - alpha)),
        )
    )


def _parse_css_color(spec: str) -> tuple[QColor, float]:
    """Devuelve (color, alfa) para `#RRGGBB` o `rgba(r, g, b, a)` de Qt."""
    spec = spec.strip()
    if spec.startswith("#"):
        return QColor(spec), 1.0
    values = [float(v) for v in re.findall(r"[\d.]+", spec)]
    return QColor(int(values[0]), int(values[1]), int(values[2])), values[3]


def _sidebar_background(dark: bool) -> QColor:
    """Compone la barra lateral translúcida sobre el fondo de la ventana."""
    sidebar, alpha = _parse_css_color(
        Styles.SIDEBAR_DARK if dark else Styles.SIDEBAR_LIGHT
    )
    return _blend(sidebar, alpha, UNDER_DARK if dark else UNDER_LIGHT)


def _active_tab_background(dark: bool) -> QColor:
    qss = Styles.get_main_style(dark)
    block = re.search(
        r'QPushButton\.nav-btn\[active="true"\]\s*\{(.*?)\}', qss, re.S
    ).group(1)
    tint, alpha = _parse_css_color(
        re.search(r"background-color:\s*([^;]+);", block).group(1)
    )
    return _blend(tint, alpha, _sidebar_background(dark))


def _active_tab_text(dark: bool) -> QColor:
    qss = Styles.get_main_style(dark)
    block = re.search(
        r'QPushButton\.nav-btn\[active="true"\]\s*\{(.*?)\}', qss, re.S
    ).group(1)
    # `background-color:` también contiene "color:", así que se excluye
    spec = re.search(r"(?<!background-)\bcolor:\s*([^;]+);", block).group(1)
    return _parse_css_color(spec)[0]


@pytest.mark.parametrize("dark", [True, False])
def test_active_nav_text_is_readable(dark):
    contrast = _contrast(_active_tab_text(dark), _active_tab_background(dark))
    assert contrast >= MIN_TEXT_CONTRAST, (
        f"el texto de la pestaña activa sólo alcanza {contrast:.2f}:1 "
        f"(mínimo {MIN_TEXT_CONTRAST}:1)"
    )


@pytest.mark.parametrize("dark", [True, False])
def test_active_nav_icon_is_readable(dark):
    background = _active_tab_background(dark)
    color, _ = _parse_css_color(
        Styles.NAV_ACTIVE_ICON_DARK if dark else Styles.NAV_ACTIVE_ICON_LIGHT
    )
    contrast = _contrast(color, background)
    assert contrast >= MIN_ICON_CONTRAST, (
        f"el icono de la pestaña activa sólo alcanza {contrast:.2f}:1"
    )


@pytest.mark.parametrize("dark", [True, False])
def test_idle_nav_items_are_readable(dark):
    background = _sidebar_background(dark)
    text, _ = _parse_css_color(
        Styles.TEXT_MUTED_DARK if dark else Styles.TEXT_MUTED_LIGHT
    )
    icon, _ = _parse_css_color(
        Styles.NAV_IDLE_ICON_DARK if dark else Styles.NAV_IDLE_ICON_LIGHT
    )
    assert _contrast(text, background) >= MIN_TEXT_CONTRAST
    assert _contrast(icon, background) >= MIN_ICON_CONTRAST


@pytest.mark.parametrize("dark", [True, False])
def test_nav_buttons_use_theme_aware_icons(qapp, dark):
    """El icono real del botón cambia con el tema, no con el color por defecto."""
    window = MainWindow()
    window.dark_mode = dark
    window._apply_theme()

    expected_active, _ = _parse_css_color(
        Styles.NAV_ACTIVE_ICON_DARK if dark else Styles.NAV_ACTIVE_ICON_LIGHT
    )
    expected_idle, _ = _parse_css_color(
        Styles.NAV_IDLE_ICON_DARK if dark else Styles.NAV_IDLE_ICON_LIGHT
    )

    def dominant_color(button) -> QColor:
        image = button.icon().pixmap(18, 18).toImage()
        best, best_alpha = QColor(0, 0, 0), -1
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                if pixel.alpha() > best_alpha:
                    best, best_alpha = pixel, pixel.alpha()
        return best

    active = next(b for b in window.nav_buttons if b.property("active") == "true")
    idle = next(b for b in window.nav_buttons if b.property("active") == "false")

    assert dominant_color(active) == expected_active
    assert dominant_color(idle) == expected_idle


def test_nav_icons_are_not_hardcoded_to_the_dark_defaults():
    """Guarda contra volver a `Icons.DEFAULT_*`, calibrados sólo para el tema oscuro."""
    window = MainWindow()
    window.dark_mode = False
    window._apply_theme()

    light_active, _ = _parse_css_color(Styles.NAV_ACTIVE_ICON_LIGHT)
    light_idle, _ = _parse_css_color(Styles.NAV_IDLE_ICON_LIGHT)
    active = next(b for b in window.nav_buttons if b.property("active") == "true")
    idle = next(b for b in window.nav_buttons if b.property("active") == "false")

    assert light_active.name() != QColor(Icons.DEFAULT_ACTIVE).name()
    assert light_idle.name() != QColor(Icons.DEFAULT_MUTED).name()
    assert (
        active.icon().pixmap(18, 18).toImage() != idle.icon().pixmap(18, 18).toImage()
    )


@pytest.mark.parametrize("dark", [True, False])
def test_nav_labels_have_no_layout_whitespace(qapp, dark):
    """El gap icono/texto lo da el QSS `nav-btn`, nunca espacios literales."""
    from application.services.i18n_service import get_i18n

    window = MainWindow()
    window.dark_mode = dark
    window._apply_theme()
    i18n = get_i18n(window.config_service)
    for lang in ("en", "de"):
        i18n.set_language(lang)
        for btn in window.nav_buttons:
            assert btn.text() == btn.text().strip(), (
                f"nav label with layout whitespace ({lang}): {btn.text()!r}"
            )
            assert not btn.icon().isNull()
