import os
import sys

import pytest

# Ensure project root directory is in sys.path for test imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from application.services.config_service import ConfigService  # noqa: E402
from application.ui.message_boxes import ThemedMessageBox  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "network: test requiring internet access (skipped offline)",
    )


@pytest.fixture(autouse=True)
def _isolated_history(monkeypatch, tmp_path):
    """
    Isolate SQLite history: tests write to a temporary database instead
    of `~/.config/SRT4U/history.db`, preventing state pollution.
    """
    monkeypatch.setenv("SRT4U_HISTORY_DB", str(tmp_path / "history.db"))


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch, tmp_path):
    """
    Isolate user configuration: tests write to a temporary directory instead
    of `~/.config/SRT4U/settings.json`, ensuring deterministic clean state.
    """
    config_dir = tmp_path / "SRT4U"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ConfigService, "_get_config_dir", lambda self: str(config_dir))


@pytest.fixture(autouse=True)
def _silence_message_boxes(monkeypatch):
    """Prevent UI QMessageBox dialogs from blocking automated test execution."""
    ok = QMessageBox.StandardButton.Ok
    # Themed wrapper used by the application
    monkeypatch.setattr(ThemedMessageBox, "information", lambda *args, **kwargs: ok)
    monkeypatch.setattr(ThemedMessageBox, "warning", lambda *args, **kwargs: ok)
    monkeypatch.setattr(ThemedMessageBox, "critical", lambda *args, **kwargs: ok)
    # Direct static QMessageBox (in case tests invoke it directly)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: ok)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app
