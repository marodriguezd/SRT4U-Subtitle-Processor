"""
Diálogos de archivo estilizados y coherentes con el tema glass de la app.

Los diálogos nativos (GTK/Windows) ignoran el QSS de la aplicación y pueden
romper el contraste con el tema oscuro; aquí se fuerza el diálogo Qt no nativo
con estilo Fusion, paleta explícita, hoja de estilos propia e iconos SVG
tematizados (los del tema del escritorio no siguen la paleta de la app).
"""

from typing import Optional

from PyQt6.QtCore import QFileInfo, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFileDialog,
    QFileIconProvider,
    QSizeGrip,
    QStyleFactory,
    QToolButton,
    QWidget,
)

from .icons import Icons
from .styles import Styles

# Botones internos del diálogo no nativo -> icono SVG equivalente
_TOOLBAR_ICONS = {
    "backButton": "arrow_left",
    "forwardButton": "arrow_right",
    "toParentButton": "arrow_up",
    "newFolderButton": "folder_plus",
    "listModeButton": "list",
    "detailModeButton": "grid",
}

# Tipos de icono del sistema de archivos -> icono SVG equivalente
_PROVIDER_ICONS = {
    QFileIconProvider.IconType.Folder: "folder",
    QFileIconProvider.IconType.File: "file",
    QFileIconProvider.IconType.Computer: "monitor",
    QFileIconProvider.IconType.Desktop: "home",
    QFileIconProvider.IconType.Trashcan: "close",
    QFileIconProvider.IconType.Network: "globe",
    QFileIconProvider.IconType.Drive: "drive",
}


class ThemedFileIconProvider(QFileIconProvider):
    """Sustituye los iconos del tema del escritorio por iconos SVG tematizados."""

    def __init__(self, dark: bool = True):
        super().__init__()
        self.dark = dark

    def icon(self, arg) -> QIcon:  # type: ignore[override]
        colors = Styles.dialog_colors(self.dark)
        if isinstance(arg, QFileInfo):
            name = "folder" if arg.isDir() else "file"
        else:
            name = _PROVIDER_ICONS.get(arg, "file")
        return Icons.get_icon(
            name, normal_color=colors["icon"], active_color=colors["accent"], size=16
        )

    def type(self, info: QFileInfo) -> str:  # type: ignore[override]
        return super().type(info)


def prepare_dialog(dialog: QFileDialog, dark: Optional[bool] = None) -> QFileDialog:
    """
    Aplica el tema de la app a un QFileDialog: estilo Fusion determinista,
    paleta explícita, QSS, iconos SVG tematizados y botones sin iconos nativos.
    """
    if dark is None:
        dark = Styles.is_dark()
    colors = Styles.dialog_colors(dark)

    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        dialog.setStyle(fusion)

    dialog.setPalette(Styles.dialog_palette(dark))
    dialog.setStyleSheet(Styles.file_dialog_style(dark))
    dialog.setIconProvider(ThemedFileIconProvider(dark))

    for button in dialog.findChildren(QToolButton):
        icon_name = _TOOLBAR_ICONS.get(button.objectName())
        if not icon_name:
            continue
        button.setIcon(
            Icons.get_icon(
                icon_name,
                normal_color=colors["icon"],
                active_color=colors["accent"],
                size=16,
            )
        )
        button.setIconSize(QSize(16, 16))

    button_box = dialog.findChild(QDialogButtonBox)
    if button_box is not None:
        # Los iconos estándar de Qt (carpeta del tema / aspa roja) no siguen la paleta
        for button in button_box.buttons():
            button.setIcon(QIcon())

    for grip in dialog.findChildren(QSizeGrip):
        grip.hide()

    return dialog


def _new_dialog(
    parent: QWidget, title: str, directory: str, name_filter: str
) -> QFileDialog:
    dialog = QFileDialog(parent, title, directory or "", name_filter)
    return prepare_dialog(dialog)


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
