import pytest
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QAbstractButton, QLabel

from application.services.i18n_service import get_i18n
from application.services.subtitle_service import SubtitleItem
from application.ui.burn_in_dialog import (
    BurnInDialog,
    BurnInOptions,
    BurnInProgressModal,
)
from application.ui.main_window import MainWindow
from application.ui.widgets import ProgressModal

LANGUAGES = ["en", "es", "pt", "de", "it", "zh-CN"]
TOLERANCE_PX = 2
FONT_SCALE = 1.5
SETTINGS_PAGE = 5
ABOUT_PAGE = 7


def _clipped_texts(root):
    """Devuelve los textos visibles que no caben en el ancho de su widget."""
    clipped = []
    widgets = list(root.findChildren(QLabel)) + list(root.findChildren(QAbstractButton))
    for widget in widgets:
        text = widget.text()
        if not text or not widget.isVisible():
            continue
        # Las etiquetas con ajuste de línea nunca se consideran recortadas
        if isinstance(widget, QLabel) and widget.wordWrap():
            continue
        if widget.fontMetrics().horizontalAdvance(text) > widget.width() + TOLERANCE_PX:
            clipped.append((type(widget).__name__, text, widget.width()))
    return clipped


@pytest.fixture
def main_window(qapp):
    window = MainWindow()
    window.show()
    qapp.processEvents()
    return window


@pytest.fixture
def scaled_app_font(qapp):
    """Aplica una fuente de aplicación ×1.5 y la restaura al terminar."""
    base = qapp.font()
    scaled = QFont(base)
    if base.pointSizeF() > 0:
        scaled.setPointSizeF(base.pointSizeF() * FONT_SCALE)
    elif base.pixelSize() > 0:
        scaled.setPixelSize(round(base.pixelSize() * FONT_SCALE))
    else:
        scaled.setPointSizeF(10 * FONT_SCALE)
    qapp.setFont(scaled)
    yield scaled
    qapp.setFont(base)
    qapp.processEvents()


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("dark", [True, False])
def test_main_window_has_no_clipped_text(main_window, lang, dark):
    get_i18n().set_language(lang, save_to_config=False)
    main_window.dark_mode = dark
    main_window._apply_theme()
    main_window.retranslate_ui()

    for page in range(main_window.stack.count()):
        main_window._switch_page(page)
        main_window.resize(main_window.minimumSizeHint())
        main_window.grab()  # fuerza el cálculo final del layout
        clipped = _clipped_texts(main_window)
        assert not clipped, (
            f"Texto recortado en {lang} (dark={dark}), página {page}: {clipped[:5]}"
        )


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("dark", [True, False])
def test_settings_and_about_no_clipped_text_at_scaled_font(
    qapp, scaled_app_font, lang, dark
):
    """Ajustes y Acerca de no recortan texto con la fuente de sistema ampliada."""
    get_i18n().set_language(lang, save_to_config=False)
    window = MainWindow()  # se crea tras aplicar la fuente para heredarla
    window.show()
    qapp.processEvents()
    try:
        window.dark_mode = dark
        window._apply_theme()
        window.retranslate_ui()

        for page in (SETTINGS_PAGE, ABOUT_PAGE):
            window._switch_page(page)
            window.resize(window.minimumSizeHint())
            window.grab()  # fuerza el cálculo final del layout
            clipped = _clipped_texts(window)
            assert not clipped, (
                f"Texto recortado con fuente ×{FONT_SCALE} en {lang} (dark={dark}), "
                f"página {page}: {clipped[:5]}"
            )
    finally:
        window.close()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_burn_in_dialog_fits_its_content(qapp, lang):
    get_i18n().set_language(lang, save_to_config=False)
    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hello world")]

    dialog = BurnInDialog(video_path="/tmp/movie.mp4", subtitle_items=items)
    try:
        dialog.show()
        qapp.processEvents()
        hint = dialog.minimumSizeHint()
        assert dialog.width() >= hint.width()
        assert dialog.height() >= hint.height()
        assert not _clipped_texts(dialog)
    finally:
        dialog.close()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_burn_in_dialog_fits_its_content_at_scaled_font(qapp, scaled_app_font, lang):
    """El diálogo de burn-in crece con la fuente ampliada y no recorta texto."""
    get_i18n().set_language(lang, save_to_config=False)
    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hello world")]

    dialog = BurnInDialog(video_path="/tmp/movie.mp4", subtitle_items=items)
    try:
        hint = dialog.minimumSizeHint()
        assert dialog.width() >= hint.width(), (
            f"Ancho insuficiente con fuente ×{FONT_SCALE} en {lang}: "
            f"{dialog.width()} < {hint.width()}"
        )
        assert dialog.height() >= hint.height(), (
            f"Alto insuficiente con fuente ×{FONT_SCALE} en {lang}: "
            f"{dialog.height()} < {hint.height()}"
        )
        assert not _clipped_texts(dialog), (
            f"Texto recortado con fuente ×{FONT_SCALE} en {lang}: "
            f"{_clipped_texts(dialog)[:5]}"
        )
    finally:
        dialog.close()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_progress_modal_fits_its_content_at_scaled_font(qapp, scaled_app_font, lang):
    """El modal de progreso no recorta texto con la fuente ampliada."""
    get_i18n().set_language(lang, save_to_config=False)

    modal = ProgressModal()
    try:
        modal.show()
        qapp.processEvents()
        clipped = _clipped_texts(modal)
        assert not clipped, (
            f"Texto recortado en el modal de progreso con fuente ×{FONT_SCALE} "
            f"en {lang}: {clipped[:5]}"
        )
    finally:
        modal.close()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_burn_in_progress_modal_fits_its_content_at_scaled_font(
    qapp, scaled_app_font, monkeypatch, lang
):
    """El modal de progreso de burn-in crece con la fuente ampliada sin recortes."""
    get_i18n().set_language(lang, save_to_config=False)
    # No arrancar FFmpeg: solo interesa la geometría del diálogo.
    monkeypatch.setattr(
        BurnInProgressModal, "_start_worker", lambda self, *a, **k: None
    )
    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hello world")]

    modal = BurnInProgressModal(
        video_path="/tmp/movie.mp4",
        output_path="/tmp/out.mp4",
        subtitle_items=items,
        options=BurnInOptions(),
    )
    try:
        modal.show()
        qapp.processEvents()
        hint = modal.minimumSizeHint()
        assert modal.width() >= hint.width(), (
            f"Ancho insuficiente con fuente ×{FONT_SCALE} en {lang}: "
            f"{modal.width()} < {hint.width()}"
        )
        assert modal.height() >= hint.height(), (
            f"Alto insuficiente con fuente ×{FONT_SCALE} en {lang}: "
            f"{modal.height()} < {hint.height()}"
        )
        clipped = _clipped_texts(modal)
        assert not clipped, (
            f"Texto recortado en el modal de burn-in con fuente ×{FONT_SCALE} "
            f"en {lang}: {clipped[:5]}"
        )
    finally:
        modal.close()


def _assert_minimum_covers_hint(dialog, name: str, lang: str) -> None:
    """Comprueba que el mínimo declarado de un diálogo cubre su contenido."""
    hint = dialog.minimumSizeHint()
    assert dialog.minimumWidth() >= hint.width(), (
        f"{name}: ancho mínimo declarado {dialog.minimumWidth()} < "
        f"contenido mínimo {hint.width()} en {lang}"
    )
    assert dialog.minimumHeight() >= hint.height(), (
        f"{name}: alto mínimo declarado {dialog.minimumHeight()} < "
        f"contenido mínimo {hint.height()} en {lang}"
    )


@pytest.mark.parametrize("lang", LANGUAGES)
def test_all_dialogs_minimum_size_covers_content(qapp, monkeypatch, lang):
    """
    Invariante de geometría: el tamaño mínimo declarado de cada diálogo de la
    app nunca queda por debajo de su `minimumSizeHint` (contenido mínimo real).
    Se comprueba tras construir y también tras mostrar (el layout puede
    recalcularse con las métricas reales de la ventana).
    """
    get_i18n().set_language(lang, save_to_config=False)
    # No arrancar FFmpeg: solo interesa la geometría del diálogo.
    monkeypatch.setattr(
        BurnInProgressModal, "_start_worker", lambda self, *a, **k: None
    )
    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hello world")]

    dialogs = [
        (
            "BurnInDialog",
            BurnInDialog(video_path="/tmp/movie.mp4", subtitle_items=items),
        ),
        ("ProgressModal", ProgressModal()),
        (
            "BurnInProgressModal",
            BurnInProgressModal(
                video_path="/tmp/movie.mp4",
                output_path="/tmp/out.mp4",
                subtitle_items=items,
                options=BurnInOptions(),
            ),
        ),
    ]
    try:
        for name, dialog in dialogs:
            _assert_minimum_covers_hint(dialog, name, lang)
            dialog.show()
            qapp.processEvents()
            _assert_minimum_covers_hint(dialog, name, lang)
    finally:
        for _, dialog in dialogs:
            dialog.close()
