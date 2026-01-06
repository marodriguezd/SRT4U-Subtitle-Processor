# AGENTS.md - SRT4U Subtitle Processor

## Project Overview

SRT4U is a PyQt6 desktop application for translating, cleaning, and converting SRT/VTT subtitle files. Built with Python 3.13+ and PyQt6, featuring a Glassmorphism UI and parallel translation engine.

**Tech Stack:** Python 3.13+, PyQt6 6.4+, deep-translator

## Build & Development Commands

### Run the Application
```bash
python main.py
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Build Executable (Windows)
```bash
.\build_exe.bat
```
Output: `dist/SRT4U.exe`

### Run Single Test (pytest)
```bash
pytest tests/ -v
pytest tests/test_file.py::test_function_name -v
```

### Run All Tests
```bash
pytest tests/
```

### Linting (if configured)
```bash
flake8 .
pylint application/
```

## Code Style Guidelines

### Imports
- Group imports: stdlib → third-party → local application
- Use absolute imports for application modules
- Example:
  ```python
  import os
  import re
  from typing import Optional, Callable, List

  from PyQt6.QtWidgets import QMainWindow, QVBoxLayout

  from ..services.subtitle_service import SubtitleService
  from .styles import Styles
  ```

### File Naming & Structure
- **Module files:** `lowercase_snake_case.py`
- **Package structure:**
  - `application/ui/` - PyQt6 UI components, glassmorphism widgets
  - `application/services/` - Pure business logic (no Qt dependencies)
  - `main.py` - Application entry point

### Naming Conventions
- **Classes:** `PascalCase` (e.g., `GlassMainWindow`, `FileService`)
- **Functions/Variables:** `snake_case` (e.g., `process_subtitles`, `input_file_path`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `PRIMARY`, `BACKGROUND`)
- **Private Methods:** Leading underscore (e.g., `_extract_blocks`)
- **Type Hints:** Use for all function parameters and return values

### Type Annotations
```python
def process_subtitles(
    self,
    file_path: str,
    translate: bool,
    target_language: Optional[str],
    progress_callback: Callable
) -> str:
```

### Docstrings
- Use triple-quoted strings for all public classes and methods
- Follow Google/NumPy style:
  ```python
  def method(self, param: int) -> bool:
      """
      Brief description.

      Args:
          param: Description of param.

      Returns:
          Description of return value.
      """
  ```

### Error Handling
- Use specific exception types (`FileNotFoundError`, `ValueError`)
- Propagate errors from services to UI via callbacks
- UI displays errors using `QMessageBox`
- Never expose secrets/logs in error messages

### Code Patterns

**Progress Callback Pattern:**
```python
progress_callback('info', "Reading file...")
progress_callback('progress', 0.5)
progress_callback('error', "Failed to read")
progress_callback('success', result)
```

**Service Layer Pattern:**
- Services in `application/services/` contain pure logic
- No Qt widgets or signals in services
- UI layer handles threading and Qt integration

**Threading:**
- Heavy processing runs in background threads
- Use `Queue` + `QTimer` for thread-safe UI updates
- Services use `concurrent.futures.ThreadPoolExecutor` for parallel translation

### UI Styling (Glassmorphism)
- Use `GlassCard`, `GlassButton`, `GlassInput` widgets
- Define styles in `application/ui/styles.py` using `Styles` class constants
- Avoid inline styles; use stylesheet constants

### Git Commit Messages
- Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`
- Keep subject under 50 characters
- Example: `feat: add parallel translation engine`

### Adding New Features
1. Add business logic in `application/services/`
2. Add UI components in `application/ui/`
3. Import services using relative imports (`from ..services import ...`)
4. Update `main.py` if adding new entry points
