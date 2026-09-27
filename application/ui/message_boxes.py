"""
QMessageBox tematizado y coherente con el tema glass de la app.

Los QMessageBox nativos ignoran el QSS de la aplicación y rompen el contraste
con el tema oscuro; este envoltorio fuerza el diálogo Qt no nativo con una
hoja de estilos propia derivada de la paleta central. La API estática replica
la de `QMessageBox` (information/warning/critical/question) para que el
reemplazo sea literal en los puntos de llamada.
"""

from PyQt6.QtWidgets import QMessageBox, QWidget

from .styles import Styles


class ThemedMessageBox:
    """Envoltorio estático de QMessageBox con el QSS glass aplicado."""

    @staticmethod
    def _show(
        icon: QMessageBox.Icon,
        parent: QWidget,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton,
        default_button: QMessageBox.StandardButton,
    ) -> QMessageBox.StandardButton:
        box = QMessageBox(parent)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        box.setDefaultButton(default_button)
        box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
        box.setStyleSheet(Styles.message_box_style())
        return box.exec()

    @staticmethod
    def information(
        parent: QWidget,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        return ThemedMessageBox._show(
            QMessageBox.Icon.Information,
            parent,
            title,
            text,
            buttons,
            default_button or QMessageBox.StandardButton.Ok,
        )

    @staticmethod
    def warning(
        parent: QWidget,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        return ThemedMessageBox._show(
            QMessageBox.Icon.Warning,
            parent,
            title,
            text,
            buttons,
            default_button or QMessageBox.StandardButton.Ok,
        )

    @staticmethod
    def critical(
        parent: QWidget,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        return ThemedMessageBox._show(
            QMessageBox.Icon.Critical,
            parent,
            title,
            text,
            buttons,
            default_button or QMessageBox.StandardButton.Ok,
        )

    @staticmethod
    def question(
        parent: QWidget,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes
        | QMessageBox.StandardButton.No,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        return ThemedMessageBox._show(
            QMessageBox.Icon.Question,
            parent,
            title,
            text,
            buttons,
            default_button or QMessageBox.StandardButton.No,
        )
