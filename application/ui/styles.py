"""
Estilos Glassmorphism con transparencias RGBA, iluminación ambiental y alto contraste.
"""

from PyQt6.QtCore import QSize
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
