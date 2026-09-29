"""
Configuración central del registro (logging) de SRT4U.

Los fallos que antes se silenciaban (`except ...: pass`, `print()`) se registran
aquí en un archivo rotativo dentro del directorio de configuración del usuario,
de modo que un problema (configuración ilegible, motor de traducción caído,
FFmpeg sin permisos, …) se pueda diagnosticar sin instrumentar la app a mano.
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
    """Devuelve el logger de la aplicación, o un logger hijo con el nombre dado."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def get_log_path(config_dir: Optional[str] = None) -> str:
    """Ruta del archivo de log (por defecto, dentro del directorio de configuración)."""
    if config_dir is None:
        # Import diferido para no crear dependencias circulares con los servicios
        from .services.config_service import ConfigService

        config_dir = ConfigService().config_dir
    return os.path.join(config_dir, LOG_FILENAME)


def install_qt_message_handler() -> None:
    """
    Redirige los mensajes de Qt (`qDebug`/`qInfo`/`qWarning`/`qCritical`/`qFatal`)
    al logger `srt4u.qt`, para que los avisos de Qt Multimedia (códecs, FFmpeg,
    audio), de los plugins de plataforma o de QSS queden junto al resto del
    diagnóstico en lugar de perderse en stderr.

    Idempotente. Debe llamarse antes de crear la `QApplication` para capturar
    también los mensajes del arranque.
    """
    global _qt_handler_installed
    if _qt_handler_installed:
        return

    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError as exc:  # Qt no disponible (p. ej. utilidades de consola)
        get_logger("qt").debug("PyQt6 no disponible: %s", exc)
        return

    logger = get_logger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        # Qt usa QtInfoMsg para avisos informativos muy ruidosos (p. ej. la versión
        # de FFmpeg de Qt Multimedia): se registran sólo en modo DEBUG.
        QtMsgType.QtInfoMsg: logging.DEBUG,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def _handler(msg_type, context, message):
        # Guarda contra recursión: nada de lo que ocurra al registrar debe volver a
        # entrar en el handler de Qt.
        if getattr(_qt_handler_state, "busy", False):
            return
        _qt_handler_state.busy = True
        try:
            category = getattr(context, "category", "") or ""
            prefix = f"[{category}] " if category and category != "default" else ""
            logger.log(levels.get(msg_type, logging.INFO), "%s%s", prefix, message)
        except Exception as exc:
            logger.debug(
                "No se pudo registrar un mensaje de Qt (%s)", type(exc).__name__
            )
        finally:
            _qt_handler_state.busy = False

    qInstallMessageHandler(_handler)
    _qt_handler_installed = True
    logger.debug("Message handler de Qt instalado")


def uninstall_qt_message_handler() -> None:
    """Restaura el manejador de mensajes por defecto de Qt (devuelve los avisos a stderr)."""
    global _qt_handler_installed
    if not _qt_handler_installed:
        return
    try:
        from PyQt6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(None)
    except ImportError as exc:
        get_logger("qt").debug("PyQt6 no disponible al desinstalar: %s", exc)
    _qt_handler_installed = False


def setup_logging(
    config_dir: Optional[str] = None,
    level: int = logging.INFO,
    console: Optional[bool] = None,
    force: bool = False,
) -> str:
    """
    Configura el logger raíz de la aplicación.

    Es idempotente: la primera llamada manda (salvo `force=True`, que reconstruye
    los handlers). Devuelve la ruta del archivo de log, aunque no se pueda crear.
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
        # No poder escribir el log nunca debe impedir que la app arranque
        logger.warning(
            "No se pudo abrir el archivo de log (%s)", type(exc).__name__
        )

    _configured_path = log_path
    return log_path
