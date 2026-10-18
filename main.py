"""
SRT4U entry point. Initializes logging, QApplication, creates the main window,
and starts the event loop.
"""

import sys
import os
import ctypes
import subprocess
import tempfile
import threading
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
            "Running without PyInstaller (%s); using the current directory", exc
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
    Log unhandled exceptions and notify the user with the log file path,
    preventing silent crashes.
    """

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        # Notification only makes sense if a QApplication instance is active
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
            # Never fail inside the exception hook itself
            logger.debug("Could not show the unexpected error notice: %s", exc)

    sys.excepthook = _hook


SMOKE_TEST_FLAG = "--smoke-test"
SMOKE_TIMEOUT_SECONDS = 90
SMOKE_FFMPEG_TIMEOUT_SECONDS = 20
SMOKE_LOG_NAME = "srt4u-smoke.log"


def _smoke_emit(message: str, log_file) -> None:
    """Write one diagnostic line to the smoke log and to stderr when present.

    ``--noconsole`` builds have no stderr, so the temporary log file is the
    reliable record; stderr is only a convenience.
    """
    line = f"[smoke] {message}"
    if sys.stderr is not None:
        print(line, file=sys.stderr, flush=True)
    log_file.write(line + "\n")
    log_file.flush()


def run_smoke_test() -> int:
    """Start the packaged GUI once, check its runtime and FFmpeg, then exit.

    Used by CI against the built artifacts. Config and history are redirected
    to a temporary location so the check never touches the user's data, and
    the function never shows dialogs or calls a translation provider.
    Returns 0 only when every check passes.
    """
    log_path = os.path.join(tempfile.gettempdir(), SMOKE_LOG_NAME)
    with open(log_path, "w", encoding="utf-8") as log_file:
        # A hung startup must not hang CI: the watchdog ends the process.
        watchdog = threading.Timer(
            SMOKE_TIMEOUT_SECONDS,
            lambda: (
                _smoke_emit("watchdog expired", log_file),
                os._exit(3),
            ),
        )
        watchdog.daemon = True
        watchdog.start()
        try:
            return _run_smoke_checks(log_file)
        except Exception as exc:
            _smoke_emit(f"FAILED: unexpected {type(exc).__name__}: {exc}", log_file)
            return 1
        finally:
            watchdog.cancel()


def _run_smoke_checks(log_file) -> int:
    """Run the individual smoke checks; return 0 when all of them pass."""
    from application.services.config_service import ConfigService
    from application.services.video_burner_service import VideoBurnerService

    failures = []

    # Redirect user data before any service is constructed.
    smoke_dir = tempfile.mkdtemp(prefix="srt4u-smoke-")
    os.environ["SRT4U_HISTORY_DB"] = os.path.join(smoke_dir, "history.db")
    ConfigService._get_config_dir = lambda self: smoke_dir

    for rel in (os.path.join("assets", "icon.png"), "LICENSE"):
        if os.path.exists(get_resource_path(rel)):
            _smoke_emit(f"resource ok: {rel}", log_file)
        else:
            failures.append(f"missing resource: {rel}")

    ffmpeg = VideoBurnerService.get_ffmpeg_path()
    if not ffmpeg:
        failures.append("FFmpeg not found")
    else:
        try:
            res = subprocess.run(
                [ffmpeg, "-version"],
                capture_output=True,
                timeout=SMOKE_FFMPEG_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"FFmpeg did not run: {type(exc).__name__}")
        else:
            if res.returncode == 0 and b"ffmpeg version" in res.stdout:
                _smoke_emit("ffmpeg -version ok", log_file)
            else:
                failures.append(f"ffmpeg -version exited {res.returncode}")

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("SRT4U")
    app.setFont(Styles.ui_font(10))
    app.setStyleSheet(Styles.tooltip_qss())
    window = GlassMainWindow()
    window.show()
    app.processEvents()
    if window.isVisible():
        _smoke_emit("main window shown", log_file)
    else:
        failures.append("main window not visible")
    window.close()
    window.deleteLater()
    app.processEvents()

    for failure in failures:
        _smoke_emit(f"FAILED: {failure}", log_file)
    if failures:
        return 1
    _smoke_emit("all checks passed", log_file)
    return 0


if __name__ == "__main__":
    if SMOKE_TEST_FLAG in sys.argv[1:]:
        sys.exit(run_smoke_test())
    log_path = setup_logging()
    # Before creating QApplication, to capture early startup messages as well
    install_qt_message_handler()
    install_excepthook(log_path)
    logger.info("Starting SRT4U (log at %s)", log_path)

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

    # Tooltips do not inherit widget QSS; styled application-wide
    app.setStyleSheet(Styles.tooltip_qss())

    processor = GlassMainWindow()
    processor.setWindowIcon(app_icon)
    processor.show()
    exit_code = app.exec()
    logger.info("SRT4U finished (exit code %s)", exit_code)
    sys.exit(exit_code)
