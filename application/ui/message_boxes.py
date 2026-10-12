"""Themed QMessageBox wrapper consistent with the application theme.

Native message boxes bypass application stylesheets and break contrast;
this wrapper forces non-native Qt dialogs with Fusion style, explicit palette,
and styling derived from the central design system.
"""

from PyQt6.QtWidgets import QMessageBox, QStyleFactory, QWidget

from .styles import Styles


class ThemedMessageBox:
    """Static QMessageBox factory with custom styling applied."""

    @staticmethod
    def build(
        icon: QMessageBox.Icon,
        parent: QWidget,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton,
        default_button: QMessageBox.StandardButton,
    ) -> QMessageBox:
        """Construct (without showing) a styled QMessageBox instance."""
        box = QMessageBox(parent)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        box.setDefaultButton(default_button)
        # QMessageBox.Option / setOption() require PyQt6 >= 6.6.1
        box.setOption(QMessageBox.Option.DontUseNativeDialog, True)

        fusion = QStyleFactory.create("Fusion")
        if fusion is not None:
            box.setStyle(fusion)
        box.setPalette(Styles.dialog_palette())
        box.setStyleSheet(Styles.message_box_style())
        return box

    @staticmethod
    def _show(
        icon: QMessageBox.Icon,
        parent: QWidget,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton,
        default_button: QMessageBox.StandardButton,
    ) -> QMessageBox.StandardButton:
        box = ThemedMessageBox.build(icon, parent, title, text, buttons, default_button)
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
