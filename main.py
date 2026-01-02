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

    app = QApplication(sys.argv)
    
    # Set application icon
    icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
    app.setWindowIcon(QIcon(icon_path))
    
    # Optional: Set application-wide font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    processor = GlassMainWindow()
    processor.show()
    sys.exit(app.exec())