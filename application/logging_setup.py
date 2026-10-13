"""Central logging configuration for SRT4U.

Operational errors and warnings are recorded to a rotating file in the
user configuration directory so issues can be diagnosed reliably without manual
instrumentation.
"""

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from typing import Optional

LOGGER_NAME = "srt4u"
LOG_FILENAME = "srt4u.log"
_MAX_BYTES = 512 * 1024
_BACKUP_COUNT = 2

_configured_path: Optional[str] = None
_qt_handler_installed = False
_qt_handler_state = threading.local()


def get_logger(name: str = "") -> logging.Logger:
    """Return the application root logger or a named child logger."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def get_log_path(config_dir: Optional[str] = None) -> str:
    """Return the path to the log file within the configuration directory."""
    if config_dir is None:
        # Deferred import to prevent circular dependencies with services
        from .services.config_service import ConfigService

        config_dir = ConfigService().config_dir
    return os.path.join(config_dir, LOG_FILENAME)


def install_qt_message_handler() -> None:
    """Redirect Qt runtime messages to the 'srt4u.qt' logger.

    Captures notices from Qt Multimedia, platform plugins, or stylesheets
    to the diagnostic log file instead of losing them on stderr.
    Idempotent. Must be invoked before QApplication instantiation.
    """
    global _qt_handler_installed
    if _qt_handler_installed:
        return

    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError as exc:
        get_logger("qt").debug("PyQt6 not available: %s", exc)
        return

    logger = get_logger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        # Qt uses QtInfoMsg for noisy notices (e.g. FFmpeg multimedia version info)
        QtMsgType.QtInfoMsg: logging.DEBUG,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def _handler(msg_type, context, message):
        # Recursion guard: prevent logging operations from re-entering the Qt handler
        if getattr(_qt_handler_state, "busy", False):
            return
        _qt_handler_state.busy = True
        try:
            category = getattr(context, "category", "") or ""
            prefix = f"[{category}] " if category and category != "default" else ""
            logger.log(levels.get(msg_type, logging.INFO), "%s%s", prefix, message)
        except Exception as exc:
            logger.debug("Failed to log Qt message (%s)", type(exc).__name__)
        finally:
            _qt_handler_state.busy = False

    qInstallMessageHandler(_handler)
    _qt_handler_installed = True
    logger.debug("Qt message handler installed")


def uninstall_qt_message_handler() -> None:
    """Restore the default Qt message handler, routing messages back to stderr."""
    global _qt_handler_installed
    if not _qt_handler_installed:
        return
    try:
        from PyQt6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(None)
    except ImportError as exc:
        get_logger("qt").debug("PyQt6 not available during uninstall: %s", exc)
    _qt_handler_installed = False


def setup_logging(
    config_dir: Optional[str] = None,
    level: int = logging.INFO,
    console: Optional[bool] = None,
    force: bool = False,
) -> str:
    """Configure the application root logger.

    Idempotent: the first call configures handlers unless force=True.
    Returns the log file path even if file creation encounters permission errors.
    """
    global _configured_path
    log_path = get_log_path(config_dir)
    logger = logging.getLogger(LOGGER_NAME)

    if _configured_path is not None and not force:
        return _configured_path

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if console is None:
        console = not getattr(sys, "frozen", False)
    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    try:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        # File logging failure must never prevent application startup
        logger.warning("Could not open log file (%s)", type(exc).__name__)

    _configured_path = log_path
    return log_path
