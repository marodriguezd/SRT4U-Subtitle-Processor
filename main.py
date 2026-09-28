"""
Punto de entrada de SRT4U. Inicializa el registro (logging), la QApplication,
crea la ventana principal y arranca el bucle de eventos.
"""

import sys
import os
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from application.logging_setup import (
    get_logger,
    install_qt_message_handler,
    setup_logging,
)
from application.ui import GlassMainWindow
from application.ui.styles import Styles

logger = get_logger("main")


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError as exc:
        logger.debug(
            "Ejecutando sin PyInstaller (%s); se usa el directorio actual", exc
        )
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def load_app_icon() -> QIcon:
    """Load application icon with multi-platform fallbacks (PNG/SVG for Linux/Mac, ICO for Windows)."""
    icon = QIcon()
    png_path = get_resource_path(os.path.join("assets", "icon.png"))
    if os.path.exists(png_path):
        icon.addFile(png_path)
    svg_path = get_resource_path(os.path.join("assets", "icon.svg"))
    if os.path.exists(svg_path):
        icon.addFile(svg_path)
    ico_path = get_resource_path(os.path.join("assets", "icon.ico"))
    if os.path.exists(ico_path):
        icon.addFile(ico_path)
    return icon


def install_excepthook(log_path: str) -> None:
    """
    Registra las excepciones no controladas y avisa al usuario indicándole el log,
    en lugar de dejar que el proceso muera en silencio.
    """

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        logger.critical(
            "Excepción no controlada", exc_info=(exc_type, exc_value, exc_tb)
        )
        # El aviso sólo tiene sentido si ya hay una QApplication viva
        if QApplication.instance() is None:
            return
        try:
            from application.services.i18n_service import t
            from application.ui.message_boxes import ThemedMessageBox

            ThemedMessageBox.critical(
                None,
                t("alert.unexpected_error_title"),
                t("alert.unexpected_error_desc", path=log_path),
            )
        except Exception as exc:
            # Nunca volver a fallar dentro del propio hook
            logger.debug("No se pudo mostrar el aviso de error inesperado: %s", exc)

    sys.excepthook = _hook


if __name__ == "__main__":
    log_path = setup_logging()
    # Antes de crear la QApplication, para capturar también los mensajes del arranque
    install_qt_message_handler()
    install_excepthook(log_path)
    logger.info("Iniciando SRT4U (log en %s)", log_path)

    # To show icon in taskbar on Windows
    if sys.platform == "win32":
        myappid = "marodriguezd.srt4u.subtitleprocessor.1.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # Ensure GLX compatibility across diverse Linux Mesa/X11 drivers
    if sys.platform.startswith("linux"):
        if "QT_XCB_GL_INTEGRATION" not in os.environ:
            os.environ["QT_XCB_GL_INTEGRATION"] = "none"

    app = QApplication(sys.argv)
    app.setApplicationName("SRT4U")
    app.setApplicationDisplayName("SRT4U Subtitle Processor")
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("srt4u")

    # Set application icon (PNG/SVG prioritized on Linux, ICO on Windows)
    app_icon = load_app_icon()
    app.setWindowIcon(app_icon)

    # Optional: Set application-wide font (platform-native family, same size)
    app.setFont(Styles.ui_font(10))

    # Tooltips no heredan QSS de widgets: se tematizan a nivel de aplicación
    app.setStyleSheet(Styles.tooltip_qss())

    processor = GlassMainWindow()
    processor.setWindowIcon(app_icon)
    processor.show()
    exit_code = app.exec()
    logger.info("SRT4U finalizado (código %s)", exit_code)
    sys.exit(exit_code)
