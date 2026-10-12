from .main_window import MainWindow, MainWindow as GlassMainWindow

# `GlassMainWindow` is preserved as a historical public alias of `MainWindow`
# (referenced by the `main.py` entry point).
__all__ = ["MainWindow", "GlassMainWindow"]
