# main.py
"""
This script is the main entry point for the SRT4U Subtitle Processor application.
It initializes the PyQt6 application and displays the main GUI.
"""
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from application.ui import GlassMainWindow

if __name__ == '__main__':
    """
    Main execution block.
    Initializes the QApplication, creates an instance of the GlassMainWindow,
    shows the GUI, and starts the application's event loop.
    """
    app = QApplication(sys.argv)
    
    # Optional: Set application-wide font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    processor = GlassMainWindow()
    processor.show()
    sys.exit(app.exec())