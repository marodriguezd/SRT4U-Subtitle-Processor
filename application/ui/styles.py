# application/ui/styles.py

class Styles:
    # Color Palette
    PRIMARY = "#007AFF"
    SECONDARY = "#5856D6"
    BACKGROUND = "rgba(10, 10, 10, 0.7)"
    GLASS_BORDER = "rgba(255, 255, 255, 0.15)"
    GLASS_BACKGROUND = "rgba(255, 255, 255, 0.05)"
    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#AAAAAA"
    ACCENT_POSITIVE = "#34C759"
    ACCENT_NEGATIVE = "#FF3B30"
    ACCENT_WARNING = "#FF9500"

    MAIN_WINDOW = f"""
    QMainWindow {{
        background: transparent;
    }}
    QWidget#CentralWidget {{
        background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, 
                                    stop:0 rgba(15, 15, 25, 255), 
                                    stop:1 rgba(40, 40, 60, 255));
    }}
    """

    GLASS_CARD = f"""
    QFrame#GlassCard {{
        background-color: {GLASS_BACKGROUND};
        border: 1px solid {GLASS_BORDER};
        border-radius: 12px;
    }}
    """

    TITLE_LABEL = f"""
    QLabel {{
        color: {TEXT_PRIMARY};
        font-weight: bold;
        font-size: 22px;
    }}
    """

    SUBTITLE_LABEL = f"""
    QLabel {{
        color: {TEXT_SECONDARY};
        font-size: 13px;
    }}
    """

    BUTTON_GLASS = f"""
    QPushButton {{
        background-color: {GLASS_BACKGROUND};
        border: 1px solid {GLASS_BORDER};
        border-radius: 8px;
        color: {TEXT_PRIMARY};
        padding: 8px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.3);
    }}
    QPushButton:pressed {{
        background-color: rgba(255, 255, 255, 0.05);
    }}
    QPushButton:disabled {{
        color: rgba(255, 255, 255, 0.2);
        background-color: rgba(255, 255, 255, 0.01);
    }}
    """

    BUTTON_PRIMARY = f"""
    QPushButton {{
        background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, 
                                    stop:0 #007AFF, stop:1 #5856D6);
        border: none;
        border-radius: 8px;
        color: white;
        padding: 10px 20px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, 
                                    stop:0 #1a87ff, stop:1 #6d6bed);
    }}
    QPushButton:pressed {{
        background: #007AFF;
    }}
    """

    INPUT_GLASS = f"""
    QLineEdit {{
        background-color: rgba(0, 0, 0, 0.2);
        border: 1px solid {GLASS_BORDER};
        border-radius: 6px;
        color: {TEXT_PRIMARY};
        padding: 6px 12px;
    }}
    QLineEdit:focus {{
        border: 1px solid {PRIMARY};
    }}
    """

    COMBO_GLASS = f"""
    QComboBox {{
        background-color: rgba(0, 0, 0, 0.2);
        border: 1px solid {GLASS_BORDER};
        border-radius: 6px;
        color: {TEXT_PRIMARY};
        padding: 4px 12px;
    }}
    QComboBox::drop-down {{
        border: none;
    }}
    QComboBox QAbstractItemView {{
        background-color: #1A1A1A;
        border: 1px solid {GLASS_BORDER};
        selection-background-color: {PRIMARY};
        color: {TEXT_PRIMARY};
    }}
    """

    CHECKBOX_GLASS = f"""
    QCheckBox {{
        color: {TEXT_PRIMARY};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid {GLASS_BORDER};
        background-color: rgba(0, 0, 0, 0.2);
    }}
    QCheckBox::indicator:checked {{
        background-color: #007AFF;
    }}
    """

    PROGRESS_GLASS = f"""
    QProgressBar {{
        background-color: rgba(0, 0, 0, 0.3);
        border: 1px solid {GLASS_BORDER};
        border-radius: 10px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, 
                                    stop:0 #007AFF, stop:1 #00E5FF);
        border-radius: 9px;
    }}
    """
