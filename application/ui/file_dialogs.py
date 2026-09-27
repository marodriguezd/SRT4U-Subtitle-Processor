"""
Diálogos de archivo estilizados y coherentes con el tema glass de la app.

Los diálogos nativos (GTK/Windows) ignoran el QSS de la aplicación y pueden
romper el contraste con el tema oscuro; aquí se fuerza el diálogo Qt no nativo
con una hoja de estilos propia derivada de la paleta central.
"""

from PyQt6.QtWidgets import QFileDialog, QWidget

from .styles import Styles


def _new_dialog(
    parent: QWidget, title: str, directory: str, name_filter: str
) -> QFileDialog:
    dialog = QFileDialog(parent, title, directory or "", name_filter)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setStyleSheet(Styles.file_dialog_style())
    return dialog


def ask_open_file(
    parent: QWidget, title: str, name_filter: str, directory: str = ""
) -> str:
    """Diálogo de apertura de un solo archivo; devuelve "" si se cancela."""
    dialog = _new_dialog(parent, title, directory, name_filter)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    if dialog.exec():
        return dialog.selectedFiles()[0]
    return ""


def ask_open_files(
    parent: QWidget, title: str, name_filter: str, directory: str = ""
) -> list:
    """Diálogo de apertura múltiple; devuelve [] si se cancela."""
    dialog = _new_dialog(parent, title, directory, name_filter)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    if dialog.exec():
        return dialog.selectedFiles()
    return []


def ask_save_file(
    parent: QWidget, title: str, name_filter: str, directory: str = ""
) -> str:
    """Diálogo de guardado; devuelve "" si se cancela."""
    dialog = _new_dialog(parent, title, directory, name_filter)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    if dialog.exec():
        return dialog.selectedFiles()[0]
    return ""
