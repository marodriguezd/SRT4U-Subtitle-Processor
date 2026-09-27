"""
Utilidades de integración con el sistema operativo para abrir archivos y
revelarlos en el explorador de archivos de forma multiplataforma.
"""

import os
import subprocess
import sys


def open_path(path: str) -> None:
    """Abre un archivo o carpeta con la aplicación predeterminada del sistema."""
    if not path:
        return
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_path(path: str) -> None:
    """Abre el gestor de archivos resaltando el archivo indicado cuando es posible."""
    if not path:
        return
    if sys.platform == "win32":
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        folder = os.path.dirname(path)
        if folder:
            subprocess.Popen(["xdg-open", folder])
