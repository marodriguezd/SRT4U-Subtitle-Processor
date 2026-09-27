"""
Estilos Glassmorphism con transparencias RGBA, iluminación ambiental y alto contraste.
"""

from typing import Dict, Optional

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QDialog


def sync_minimum_size(dialog: QDialog, floor: QSize) -> None:
    """
    Fija el tamaño mínimo real de un diálogo según su contenido ya construido,
    con un suelo de diseño como cota inferior. Evita que el mínimo declarado
    se quede corto respecto al `minimumSizeHint` real (recortes) si el
    contenido crece en futuras iteraciones.
    """
    dialog.ensurePolished()
    dialog.layout().activate()
    dialog.setMinimumSize(dialog.minimumSizeHint().expandedTo(floor))


class Styles:
    # Paleta Dark Glass
    BG_DARK_GRADIENT = "qradialgradient(cx:0.5, cy:0.2, radius:0.85, fx:0.5, fy:0.2, stop:0 #1E1B4B, stop:0.45 #0F1426, stop:1 #080B12)"
    SIDEBAR_DARK = "rgba(13, 19, 36, 0.75)"
    CARD_DARK = "rgba(20, 27, 48, 0.68)"
    CARD_BORDER_DARK = "rgba(99, 102, 241, 0.22)"
    CARD_BORDER_HOVER_DARK = "rgba(129, 140, 248, 0.55)"
    TEXT_MAIN_DARK = "#F8FAFC"
    TEXT_MUTED_DARK = "#94A3B8"
    PRIMARY = "#6366F1"
    PRIMARY_HOVER = "#4F46E5"
    PRIMARY_LIGHT = "rgba(99, 102, 241, 0.25)"
    ACCENT = "#8B5CF6"
    ACCENT_HOVER = "#7C3AED"
    ACCENT_LIGHT = "#A78BFA"
    SUCCESS = "#10B981"
    DANGER = "#EF4444"
    INFO = "#38BDF8"

    # Superficies y bordes compartidos por los diálogos y paneles oscuros
    SURFACE = "#0F172A"
    SURFACE_DEEP = "#0B0F19"
    SURFACE_ALT = "#111827"
    SURFACE_RAISED = "#1E293B"
    BORDER = "#334155"
    BORDER_SUBTLE = "#1F2937"

    # Texto
    TEXT = "#F8FAFC"
    TEXT_SUBTLE = "#CBD5E1"
    TEXT_MUTED = "#94A3B8"
    TEXT_FAINT = "#64748B"

    # Paleta Light Glass
    BG_LIGHT_GRADIENT = "qradialgradient(cx:0.5, cy:0.2, radius:0.9, fx:0.5, fy:0.2, stop:0 #EEF2FF, stop:0.5 #F8FAFC, stop:1 #F1F5F9)"
    SIDEBAR_LIGHT = "rgba(255, 255, 255, 0.85)"
    CARD_LIGHT = "rgba(255, 255, 255, 0.88)"
    CARD_BORDER_LIGHT = "rgba(226, 232, 240, 0.95)"
    TEXT_MAIN_LIGHT = "#0F172A"
    TEXT_SUBTLE_LIGHT = "#334155"
    TEXT_MUTED_LIGHT = "#64748B"

    # Colores de texto que usan los estilos inline de las vistas (tema oscuro)
    INLINE_TEXT_DARK = "#F8FAFC"
    INLINE_MUTED_DARK = "#94A3B8"
    INLINE_SUBTLE_DARK = "#CBD5E1"
    INLINE_ACCENT_DARK = "#A78BFA"
    INLINE_ACCENT2_DARK = "#818CF8"
    INLINE_SUCCESS_DARK = "#10B981"
    INLINE_SUCCESS_LIGHT = "#047857"

    # Superficies de widgets deliberadamente oscuros (reproductor, tarjetas de vídeo)
    PERMANENT_DARK_SURFACES = ("#070B14", "#0B0F19")

    # Tema activo de la aplicación. Lo mantiene `MainWindow._apply_theme()` para
    # que los diálogos del sistema (archivos, mensajes) se pinten en el tema correcto.
    _CURRENT_DARK = True

    @classmethod
    def set_dark(cls, dark: bool) -> None:
        """Registra el tema activo de la aplicación."""
        cls._CURRENT_DARK = bool(dark)

    @classmethod
    def is_dark(cls) -> bool:
        """Devuelve True si el tema activo de la aplicación es el oscuro."""
        return cls._CURRENT_DARK

    @classmethod
    def dialog_colors(cls, dark: Optional[bool] = None) -> Dict[str, str]:
        """
        Colores de superficie/texto/acento para los diálogos del sistema, en el
        tema indicado (por defecto, el tema activo de la aplicación).
        """
        if dark is None:
            dark = cls.is_dark()
        if dark:
            return {
                "bg": cls.SURFACE_DEEP,
                "surface": cls.SURFACE,
                "surface_alt": cls.SURFACE_ALT,
                "raised": cls.SURFACE_RAISED,
                "border": cls.BORDER,
                "border_subtle": cls.BORDER_SUBTLE,
                "text": cls.TEXT,
                "subtle": cls.TEXT_SUBTLE,
                "muted": cls.TEXT_MUTED,
                "faint": cls.TEXT_FAINT,
                "accent": cls.ACCENT,
                "accent_hover": cls.ACCENT_HOVER,
                "primary": cls.PRIMARY,
                "primary_hover": cls.PRIMARY_HOVER,
                "selection": cls.PRIMARY,
                "selection_text": "#FFFFFF",
                "icon": cls.TEXT_SUBTLE,
            }
        return {
            "bg": "#FFFFFF",
            "surface": "#F8FAFC",
            "surface_alt": "#F1F5F9",
            "raised": "#EEF2FF",
            "border": "#CBD5E1",
            "border_subtle": "#E2E8F0",
            "text": cls.TEXT_MAIN_LIGHT,
            "subtle": cls.TEXT_SUBTLE_LIGHT,
            "muted": cls.TEXT_MUTED_LIGHT,
            "faint": "#94A3B8",
            "accent": cls.PRIMARY,
            "accent_hover": cls.PRIMARY_HOVER,
            "primary": cls.PRIMARY,
            "primary_hover": cls.PRIMARY_HOVER,
            "selection": cls.PRIMARY,
            "selection_text": "#FFFFFF",
            "icon": cls.TEXT_SUBTLE_LIGHT,
        }

    @classmethod
    def dialog_palette(cls, dark: Optional[bool] = None) -> QPalette:
        """
        Paleta explícita para diálogos top-level (QFileDialog/QMessageBox).

        Aunque el QSS cubre la mayoría de widgets, hay elementos que se pintan
        con la paleta (delegados de listas, iconos estándar del estilo, color de
        selección); sin fijarla, esos elementos usan el azul por defecto de Qt
        (`#308cc6`) y los colores del tema del escritorio.
        """
        c = cls.dialog_colors(dark)
        palette = QPalette()
        groups = (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive)
        roles = {
            QPalette.ColorRole.Window: c["bg"],
            QPalette.ColorRole.WindowText: c["text"],
            QPalette.ColorRole.Base: c["surface"],
            QPalette.ColorRole.AlternateBase: c["raised"],
            QPalette.ColorRole.Text: c["text"],
            QPalette.ColorRole.Button: c["raised"],
            QPalette.ColorRole.ButtonText: c["text"],
            QPalette.ColorRole.BrightText: c["accent"],
            QPalette.ColorRole.Highlight: c["selection"],
            QPalette.ColorRole.HighlightedText: c["selection_text"],
            QPalette.ColorRole.ToolTipBase: c["raised"],
            QPalette.ColorRole.ToolTipText: c["text"],
            QPalette.ColorRole.PlaceholderText: c["muted"],
            QPalette.ColorRole.Link: c["primary"],
        }
        for group in groups:
            for role, color in roles.items():
                palette.setColor(group, role, QColor(color))
        # Estado deshabilitado: texto atenuado pero legible sobre la superficie
        for role in (
            QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText,
            QPalette.ColorRole.WindowText,
        ):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
        return palette

    @classmethod
    def message_box_style(cls, dark: Optional[bool] = None) -> str:
        """QSS para los QMessageBox no nativos, coherente con la paleta glass."""
        c = cls.dialog_colors(dark)
        return f"""
            QMessageBox {{
                background-color: {c["bg"]};
                color: {c["text"]};
            }}
            QMessageBox QLabel {{
                color: {c["subtle"]};
                font-size: 13px;
                background: transparent;
                selection-background-color: {c["selection"]};
                selection-color: {c["selection_text"]};
            }}
            QMessageBox QLabel#qt_msgbox_label {{
                color: {c["text"]};
                font-size: 14px;
                font-weight: 600;
            }}
            QMessageBox QLabel#qt_msgbox_informativelabel {{
                color: {c["muted"]};
            }}
            QMessageBox QPushButton {{
                background-color: {c["raised"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
                padding: 7px 18px;
                font-weight: 600;
                min-width: 64px;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {c["border"]};
                border-color: {c["accent"]};
            }}
            QMessageBox QPushButton:default {{
                background-color: {c["accent"]};
                color: #FFFFFF;
                border: none;
                font-weight: 700;
            }}
            QMessageBox QPushButton:default:hover {{ background-color: {c["accent_hover"]}; }}
        """

    @classmethod
    def tooltip_qss(cls, dark: Optional[bool] = None) -> str:
        """QSS de nivel de aplicación para tooltips (no heredan estilos de widgets)."""
        c = cls.dialog_colors(dark)
        return f"""
            QToolTip {{
                background-color: {c["raised"]};
                color: {c["text"]};
                border: 1px solid {c["accent"]};
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }}
        """

    @classmethod
    def file_dialog_style(cls, dark: Optional[bool] = None) -> str:
        """
        QSS para los QFileDialog no nativos, coherente con el tema glass activo.

        Las reglas se limitan al propio diálogo (`QFileDialog` y sus descendientes)
        para no pintar indiscriminadamente widgets internos de Qt que gestionan su
        fondo por sí mismos (viewports, splitters, grip).
        """
        c = cls.dialog_colors(dark)
        return f"""
            QFileDialog {{
                background-color: {c["bg"]};
                color: {c["text"]};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
            }}
            QFileDialog QLabel {{
                color: {c["subtle"]};
                background: transparent;
            }}
            QFileDialog QLineEdit, QFileDialog QComboBox {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
                padding: 6px 10px;
                selection-background-color: {c["selection"]};
                selection-color: {c["selection_text"]};
            }}
            QFileDialog QLineEdit:hover, QFileDialog QComboBox:hover {{
                border-color: {c["accent"]};
            }}
            QFileDialog QLineEdit:focus, QFileDialog QComboBox:focus {{
                border-color: {c["accent"]};
            }}
            QFileDialog QComboBox QAbstractItemView {{
                background-color: {c["raised"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                selection-background-color: {c["selection"]};
                selection-color: {c["selection_text"]};
                outline: none;
            }}
            QFileDialog QPushButton {{
                background-color: {c["raised"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: 600;
            }}
            QFileDialog QPushButton:hover {{
                background-color: {c["border"]};
                border-color: {c["accent"]};
            }}
            QFileDialog QPushButton:default {{
                background-color: {c["accent"]};
                color: #FFFFFF;
                border: none;
                font-weight: 700;
            }}
            QFileDialog QPushButton:default:hover {{ background-color: {c["accent_hover"]}; }}
            QFileDialog QToolButton {{
                background-color: transparent;
                color: {c["text"]};
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 3px;
            }}
            QFileDialog QToolButton:hover {{
                background-color: {c["raised"]};
                border-color: {c["border"]};
            }}
            QFileDialog QToolButton:pressed, QFileDialog QToolButton:checked {{
                background-color: {c["border"]};
                border-color: {c["accent"]};
            }}
            QFileDialog QToolButton::menu-indicator {{ image: none; }}
            QFileDialog QListView, QFileDialog QTreeView, QFileDialog QTableView {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
                alternate-background-color: {c["surface_alt"]};
                selection-background-color: {c["selection"]};
                selection-color: {c["selection_text"]};
                outline: none;
            }}
            QFileDialog QListView::item, QFileDialog QTreeView::item {{
                color: {c["text"]};
                padding: 3px 4px;
            }}
            QFileDialog QListView::item:selected, QFileDialog QTreeView::item:selected {{
                background-color: {c["selection"]};
                color: {c["selection_text"]};
            }}
            QFileDialog QHeaderView::section {{
                background-color: {c["raised"]};
                color: {c["subtle"]};
                border: none;
                border-bottom: 1px solid {c["border"]};
                padding: 6px;
            }}
            QFileDialog QSplitter::handle {{ background-color: {c["border_subtle"]}; }}
            QFileDialog QScrollBar:vertical {{
                background: {c["bg"]};
                width: 10px;
                margin: 0;
            }}
            QFileDialog QScrollBar::handle:vertical {{
                background: {c["border"]};
                border-radius: 5px;
                min-height: 30px;
            }}
            QFileDialog QScrollBar::handle:vertical:hover {{ background: {c["muted"]}; }}
            QFileDialog QScrollBar::add-line:vertical, QFileDialog QScrollBar::sub-line:vertical {{ height: 0; }}
            QFileDialog QScrollBar:horizontal {{
                background: {c["bg"]};
                height: 10px;
                margin: 0;
            }}
            QFileDialog QScrollBar::handle:horizontal {{
                background: {c["border"]};
                border-radius: 5px;
                min-width: 30px;
            }}
            QFileDialog QScrollBar::add-line:horizontal, QFileDialog QScrollBar::sub-line:horizontal {{ width: 0; }}
            QFileDialog QMenu {{
                background-color: {c["raised"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
            }}
            QFileDialog QMenu::item:selected {{
                background-color: {c["selection"]};
                color: {c["selection_text"]};
            }}
        """

    @classmethod
    def retint_inline_text(cls, root, dark: bool) -> None:
        """
        Adapta los colores de texto definidos inline en las vistas al tema activo.
        Solo afecta a etiquetas/botones que heredan el fondo del tema (no a widgets
        sobre superficies permanentemente oscuras como el reproductor de vídeo).
        """
        from PyQt6.QtWidgets import QLabel, QAbstractButton

        main = cls.INLINE_TEXT_DARK if dark else cls.TEXT_MAIN_LIGHT
        muted = cls.INLINE_MUTED_DARK if dark else cls.TEXT_MUTED_LIGHT
        subtle = cls.INLINE_SUBTLE_DARK if dark else cls.TEXT_SUBTLE_LIGHT
        accent = cls.INLINE_ACCENT_DARK if dark else cls.PRIMARY
        accent2 = cls.INLINE_ACCENT2_DARK if dark else cls.PRIMARY_HOVER
        success = cls.INLINE_SUCCESS_DARK if dark else cls.INLINE_SUCCESS_LIGHT

        candidates = list(root.findChildren(QLabel)) + list(
            root.findChildren(QAbstractButton)
        )
        for widget in candidates:
            sheet = widget.styleSheet()
            if not sheet:
                continue
            # Los widgets con fondo propio o sobre superficies oscuras fijas no se retocan
            if "background" in sheet and "transparent" not in sheet:
                continue
            if cls._has_permanent_dark_ancestor(widget):
                continue

            original = widget.property("_theme_source_style")
            if original is None:
                original = sheet
                widget.setProperty("_theme_source_style", original)

            new_sheet = (
                original.replace(cls.INLINE_TEXT_DARK, main)
                .replace(cls.INLINE_MUTED_DARK, muted)
                .replace(cls.INLINE_SUBTLE_DARK, subtle)
                .replace(cls.INLINE_ACCENT_DARK, accent)
                .replace(cls.INLINE_ACCENT2_DARK, accent2)
                .replace(cls.INLINE_SUCCESS_DARK, success)
            )
            if new_sheet != sheet:
                widget.setStyleSheet(new_sheet)

    @classmethod
    def _has_permanent_dark_ancestor(cls, widget) -> bool:
        parent = widget.parentWidget()
        while parent is not None:
            parent_sheet = parent.styleSheet() if hasattr(parent, "styleSheet") else ""
            if parent_sheet and any(
                surface in parent_sheet for surface in cls.PERMANENT_DARK_SURFACES
            ):
                return True
            parent = parent.parentWidget()
        return False

    @classmethod
    def get_main_style(cls, dark: bool = True) -> str:
        bg = cls.BG_DARK_GRADIENT if dark else cls.BG_LIGHT_GRADIENT
        sidebar_bg = cls.SIDEBAR_DARK if dark else cls.SIDEBAR_LIGHT
        card_bg = cls.CARD_DARK if dark else cls.CARD_LIGHT
        border = cls.CARD_BORDER_DARK if dark else cls.CARD_BORDER_LIGHT
        border_hover = cls.CARD_BORDER_HOVER_DARK if dark else "#CBD5E1"
        text = cls.TEXT_MAIN_DARK if dark else cls.TEXT_MAIN_LIGHT
        muted = cls.TEXT_MUTED_DARK if dark else cls.TEXT_MUTED_LIGHT
        drop_bg = "rgba(15, 23, 42, 0.55)" if dark else "rgba(255, 255, 255, 0.6)"
        drop_border = "rgba(99, 102, 241, 0.5)" if dark else "#818CF8"

        return f"""
        QMainWindow, QWidget#CentralWidget {{
            background: {bg};
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            color: {text};
        }}

        QLabel {{
            color: {text};
        }}

        QWidget#Sidebar {{
            background-color: {sidebar_bg};
            border-right: 1px solid {border};
        }}

        QPushButton.nav-btn {{
            background-color: transparent;
            color: {muted};
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 10px 14px;
            font-size: 13px;
            font-weight: 500;
            text-align: left;
        }}
        QPushButton.nav-btn:hover {{
            background-color: {"rgba(255, 255, 255, 0.06)" if dark else "rgba(0, 0, 0, 0.04)"};
            color: {text};
            border-color: {border};
        }}
        QPushButton.nav-btn[active="true"] {{
            background-color: {cls.PRIMARY_LIGHT};
            color: #C7D2FE;
            font-weight: 600;
            border: 1px solid {cls.PRIMARY};
        }}

        QFrame#CardContainer, QFrame.ModernCard {{
            background-color: {card_bg};
            border: 1px solid {border};
            border-radius: 14px;
        }}
        QFrame#CardContainer:hover, QFrame.ModernCard:hover {{
            border-color: {border_hover};
        }}

        QFrame#DropZone {{
            background-color: {drop_bg};
            border: 2px dashed {drop_border};
            border-radius: 16px;
        }}
        QFrame#DropZone:hover {{
            background-color: {"rgba(99, 102, 241, 0.18)" if dark else "rgba(99, 102, 241, 0.08)"};
            border-color: {cls.PRIMARY};
        }}

        QComboBox {{
            background-color: {card_bg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
            color: {text};
            min-height: 24px;
        }}
        QComboBox:hover {{
            border-color: {cls.PRIMARY};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 25px;
            border-left: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: {"#111827" if dark else "#FFFFFF"};
            border: 1px solid {border};
            border-radius: 8px;
            selection-background-color: {cls.PRIMARY_LIGHT};
            selection-color: {text};
            color: {text};
            outline: none;
            padding: 4px;
        }}

        QPushButton#PrimaryBtn {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {cls.PRIMARY}, stop:1 {cls.ACCENT});
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 12px 24px;
            font-size: 15px;
            font-weight: 700;
            min-height: 24px;
        }}
        QPushButton#PrimaryBtn:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {cls.PRIMARY_HOVER}, stop:1 #7C3AED);
            border-color: rgba(255, 255, 255, 0.3);
        }}
        QPushButton#PrimaryBtn:pressed {{
            background-color: #3730A3;
        }}

        QPushButton.secondary-btn {{
            background-color: {"rgba(255, 255, 255, 0.06)" if dark else "#FFFFFF"};
            border: 1px solid {border};
            border-radius: 10px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 500;
            color: {text};
        }}
        QPushButton.secondary-btn:hover {{
            background-color: {"rgba(255, 255, 255, 0.12)" if dark else "#F8FAFC"};
            border-color: {cls.PRIMARY};
        }}

        QLineEdit {{
            background-color: {card_bg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
            color: {text};
        }}
        QLineEdit:focus {{
            border-color: {cls.PRIMARY};
        }}

        QTableWidget {{
            background-color: {card_bg};
            border: 1px solid {border};
            border-radius: 8px;
            color: {text};
            gridline-color: {border};
        }}
        QHeaderView::section {{
            background-color: {"rgba(13, 19, 36, 0.9)" if dark else "#F1F5F9"};
            color: {muted};
            padding: 8px;
            border: none;
            font-weight: 600;
        }}
        """
