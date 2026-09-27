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
from logging.handlers import RotatingFileHandler
from typing import Optional

LOGGER_NAME = "srt4u"
LOG_FILENAME = "srt4u.log"
_MAX_BYTES = 512 * 1024
_BACKUP_COUNT = 2

_configured_path: Optional[str] = None


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
        logger.warning("No se pudo abrir el archivo de log %s: %s", log_path, exc)

    _configured_path = log_path
    return log_path
