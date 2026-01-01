# application/ui/widgets.py
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QCheckBox, QComboBox, QProgressBar
from PyQt6.QtCore import Qt
from .styles import Styles

class GlassCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setStyleSheet(Styles.GLASS_CARD)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

class GlassButton(QPushButton):
    def __init__(self, text, primary=False, parent=None):
        super().__init__(text, parent)
        if primary:
            self.setStyleSheet(Styles.BUTTON_PRIMARY)
        else:
            self.setStyleSheet(Styles.BUTTON_GLASS)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

class GlassInput(QLineEdit):
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(Styles.INPUT_GLASS)

class IconButton(QPushButton):
    def __init__(self, icon_path, parent=None):
        super().__init__(parent)
        # Placeholder for icon usage, for now just a stylized button
        self.setFixedSize(30, 30)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border-radius: 15px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.1);
            }}
        """)
