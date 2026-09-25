# application/ui/styles.py
"""
Estilos Glassmorphism Dark con alto contraste, legibilidad y fidelidad al mockup.
"""

class Styles:
    # Paleta Dark
    BG_DARK = "#0A0E17"
    SIDEBAR_DARK = "#0D1322"
    CARD_DARK = "#141B2D"
    CARD_BORDER_DARK = "#25304B"
    TEXT_MAIN_DARK = "#F8FAFC"
    TEXT_MUTED_DARK = "#94A3B8"
    PRIMARY = "#6366F1"
    PRIMARY_HOVER = "#4F46E5"
    PRIMARY_LIGHT = "rgba(99, 102, 241, 0.2)"
    ACCENT = "#8B5CF6"
    SUCCESS = "#10B981"

    # Paleta Light
    BG_LIGHT = "#F8FAFC"
    SIDEBAR_LIGHT = "#FFFFFF"
    CARD_LIGHT = "#FFFFFF"
    CARD_BORDER_LIGHT = "#E2E8F0"
    TEXT_MAIN_LIGHT = "#0F172A"
    TEXT_MUTED_LIGHT = "#64748B"

    @classmethod
    def get_main_style(cls, dark: bool = True) -> str:
        bg = cls.BG_DARK if dark else cls.BG_LIGHT
        sidebar_bg = cls.SIDEBAR_DARK if dark else cls.SIDEBAR_LIGHT
        card_bg = cls.CARD_DARK if dark else cls.CARD_LIGHT
        border = cls.CARD_BORDER_DARK if dark else cls.CARD_BORDER_LIGHT
        text = cls.TEXT_MAIN_DARK if dark else cls.TEXT_MAIN_LIGHT
        muted = cls.TEXT_MUTED_DARK if dark else cls.TEXT_MUTED_LIGHT
        drop_bg = "#0F1626" if dark else "#F8FAFC"
        drop_border = "#4F46E5" if dark else "#818CF8"

        return f"""
        QMainWindow, QWidget#CentralWidget {{
            background-color: {bg};
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            color: {text};
        }}

        QLabel {{
            color: {text};
        }}

        QLabel.muted {{
            color: {muted};
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
            background-color: {"rgba(255, 255, 255, 0.05)" if dark else "#F1F5F9"};
            color: {text};
        }}
        QPushButton.nav-btn[active="true"] {{
            background-color: {cls.PRIMARY_LIGHT};
            color: #C7D2FE;
            font-weight: 600;
            border: 1px solid #4F46E5;
        }}

        QFrame#CardContainer, QFrame.ModernCard {{
            background-color: {card_bg};
            border: 1px solid {border};
            border-radius: 14px;
        }}

        QFrame#DropZone {{
            background-color: {drop_bg};
            border: 2px dashed {drop_border};
            border-radius: 16px;
        }}
        QFrame#DropZone:hover {{
            background-color: {"rgba(99, 102, 241, 0.15)" if dark else "#EEF2FF"};
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
            background-color: {card_bg};
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
            border: none;
            border-radius: 12px;
            padding: 12px 24px;
            font-size: 15px;
            font-weight: 700;
            min-height: 22px;
        }}
        QPushButton#PrimaryBtn:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {cls.PRIMARY_HOVER}, stop:1 #7C3AED);
        }}
        QPushButton#PrimaryBtn:pressed {{
            background-color: #3730A3;
        }}

        QPushButton.secondary-btn {{
            background-color: {"rgba(255, 255, 255, 0.05)" if dark else "#FFFFFF"};
            border: 1px solid {border};
            border-radius: 10px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 500;
            color: {text};
        }}
        QPushButton.secondary-btn:hover {{
            background-color: {"rgba(255, 255, 255, 0.1)" if dark else "#F8FAFC"};
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
            background-color: {"#0D1322" if dark else "#F1F5F9"};
            color: {muted};
            padding: 8px;
            border: none;
            font-weight: 600;
        }}
        """
