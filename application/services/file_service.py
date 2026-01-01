# application/services/file_service.py
"""
This module provides a service for handling file-related operations,
such as creating temporary directories and managing file dialogs.
"""
import os
import shutil
import tempfile
from typing import Any


class FileService:
    """
    A service class for managing file operations.
    """
    def __init__(self):
        """
        Initializes the FileService and creates a temporary directory for use by the application.
        """
        self.temp_directory = self._create_temp_directory()

    def _create_temp_directory(self) -> str:
        """
        Creates a dedicated temporary directory for the application.

        Returns:
            str: The absolute path to the created temporary directory.
        """
        temp_dir = os.path.join(tempfile.gettempdir(), 'srt4u')
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

    def cleanup_temp(self):
        """
        Removes the temporary directory and all its contents.
        """
        if os.path.exists(self.temp_directory):
            shutil.rmtree(self.temp_directory)