import os
import sys

import pytest

# Asegurar que el directorio raíz del proyecto esté en sys.path para los tests
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from application.services.config_service import ConfigService  # noqa: E402
from application.ui.message_boxes import ThemedMessageBox  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "network: test que requiere acceso a Internet (se omite si no hay red)",
    )


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch, tmp_path):
    """
    Aísla la configuración de usuario: los tests escriben en un directorio temporal
    en lugar de `~/.config/SRT4U/settings.json`, evitando que la suite modifique
    las preferencias reales del usuario o dependa del estado previo en disco.
    """
    config_dir = tmp_path / "SRT4U"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ConfigService, "_get_config_dir", lambda self: str(config_dir))


@pytest.fixture(autouse=True)
def _silence_message_boxes(monkeypatch):
    """Evita que los QMessageBox de la UI bloqueen la ejecución de los tests."""
    ok = QMessageBox.StandardButton.Ok
    # Envoltorio tematizado usado por la aplicación
    monkeypatch.setattr(ThemedMessageBox, "information", lambda *args, **kwargs: ok)
    monkeypatch.setattr(ThemedMessageBox, "warning", lambda *args, **kwargs: ok)
    monkeypatch.setattr(ThemedMessageBox, "critical", lambda *args, **kwargs: ok)
    # QMessageBox estático directo (por si algún test lo usa explícitamente)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: ok)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app
