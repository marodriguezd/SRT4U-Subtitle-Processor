import sys
import os
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from application.ui import GlassMainWindow

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def load_app_icon() -> QIcon:
    """Load application icon with multi-platform fallbacks (PNG/SVG for Linux/Mac, ICO for Windows)."""
    icon = QIcon()
    png_path = get_resource_path(os.path.join("assets", "icon.png"))
    if os.path.exists(png_path):
        icon.addFile(png_path)
    svg_path = get_resource_path(os.path.join("assets", "icon.svg"))
    if os.path.exists(svg_path):
        icon.addFile(svg_path)
    ico_path = get_resource_path(os.path.join("assets", "icon.ico"))
    if os.path.exists(ico_path):
        icon.addFile(ico_path)
    return icon

if __name__ == '__main__':
    """
    Main execution block.
    Initializes the QApplication, creates an instance of the GlassMainWindow,
    shows the GUI, and starts the application's event loop.
    """
    # To show icon in taskbar on Windows
    if sys.platform == 'win32':
        myappid = 'marodriguezd.srt4u.subtitleprocessor.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # Ensure GLX compatibility across diverse Linux Mesa/X11 drivers
    if sys.platform.startswith('linux'):
        if 'QT_XCB_GL_INTEGRATION' not in os.environ:
            os.environ['QT_XCB_GL_INTEGRATION'] = 'none'

    app = QApplication(sys.argv)
    app.setApplicationName("SRT4U")
    app.setApplicationDisplayName("SRT4U Subtitle Processor")
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("srt4u")
    
    # Set application icon (PNG/SVG prioritized on Linux, ICO on Windows)
    app_icon = load_app_icon()
    app.setWindowIcon(app_icon)
    
    # Optional: Set application-wide font
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
    
    processor = GlassMainWindow()
    processor.setWindowIcon(app_icon)
    processor.show()
    sys.exit(app.exec())