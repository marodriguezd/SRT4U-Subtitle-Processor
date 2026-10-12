"""Cross-platform operating system utilities for opening and revealing files."""

import os
import subprocess
import sys


def open_path(path: str) -> None:
    """Open a file or directory using the system default application."""
    if not path:
        return
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_path(path: str) -> None:
    """Open the system file manager highlighting the target file when supported."""
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
