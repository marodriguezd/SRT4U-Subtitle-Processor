from .main_window import MainWindow, MainWindow as GlassMainWindow

# `GlassMainWindow` se mantiene como alias público histórico de `MainWindow`
# (usado por el punto de entrada `main.py`).
__all__ = ["MainWindow", "GlassMainWindow"]
