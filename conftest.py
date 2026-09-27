import os
import sys

import pytest

# Asegurar que el directorio raíz del proyecto esté en sys.path para los tests
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture(autouse=True)
def _silence_message_boxes(monkeypatch):
    """Evita que los QMessageBox de la UI bloqueen la ejecución de los tests."""
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app
