import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_analyze_and_qa_run_when_pyqt_imports_are_blocked():
    script = r"""
import builtins
import io
import json
import sys
from contextlib import redirect_stdout
from application.cli import main

original_import = builtins.__import__
def block_qt(name, *args, **kwargs):
    if name == 'PyQt6' or name.startswith('PyQt6.'):
        raise AssertionError('headless command attempted to import PyQt6')
    return original_import(name, *args, **kwargs)
builtins.__import__ = block_qt
for command in ('analyze', 'qa'):
    output = io.StringIO()
    with redirect_stdout(output):
        assert main([command, 'tests/fixtures/sample.srt', '--json']) == 0
    report = json.loads(output.getvalue())
    assert ('analytics' in report) if command == 'analyze' else ('findings' in report)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_analytics_service_imports_without_pyqt6():
    script = """
import sys
from application.services.subtitle_analytics import SubtitleAnalyticsService
from application.services.subtitle_qa import SubtitleQA
import application.cli
assert not any(name == 'PyQt6' or name.startswith('PyQt6.') for name in sys.modules)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
