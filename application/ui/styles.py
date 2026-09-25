# application/ui/styles.py
"""
Estilos Glassmorphism con transparencias RGBA, iluminación ambiental y alto contraste.
"""

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
    SUCCESS = "#10B981"

    # Paleta Light Glass
    BG_LIGHT_GRADIENT = "qradialgradient(cx:0.5, cy:0.2, radius:0.9, fx:0.5, fy:0.2, stop:0 #EEF2FF, stop:0.5 #F8FAFC, stop:1 #F1F5F9)"
    SIDEBAR_LIGHT = "rgba(255, 255, 255, 0.85)"
    CARD_LIGHT = "rgba(255, 255, 255, 0.88)"
    CARD_BORDER_LIGHT = "rgba(226, 232, 240, 0.95)"
    TEXT_MAIN_LIGHT = "#0F172A"
    TEXT_MUTED_LIGHT = "#64748B"

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
