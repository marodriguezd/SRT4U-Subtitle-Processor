"""
Smoke test for `tools/regenerate_screenshots.py`: runs the real utility in a
subprocess (offscreen platform) so it cannot silently rot over time, and
verifies that its default gallery covers every interface language declared by
the i18n service.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from application.services.i18n_service import I18nService

TOOL = Path(__file__).resolve().parent.parent / "tools" / "regenerate_screenshots.py"


def _load_tool():
    """Load the tool module to read its constants (no QApplication is created)."""
    spec = importlib.util.spec_from_file_location("regenerate_screenshots", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected_shots(tool) -> set:
    """Expected default gallery, derived from the tool's own constants."""
    names = set()
    for lang in tool.WINDOW_LANGS:
        for theme in ("dark", "light"):
            for _, page in tool.WINDOW_PAGES:
                names.add(f"{page}_{lang}_{theme}.png")
    for lang in tool.DIALOG_LANGS:
        names.add(f"burn_{lang}.png")
        names.add(f"messagebox_{lang}.png")
        for theme in ("dark", "light"):
            names.add(f"filedialog_{lang}_{theme}.png")
    for lang in tool.DIALOG_LANGS[:2]:
        names.add(f"progress_{lang}.png")
        names.add(f"burnprogress_{lang}.png")
    return names


def test_screenshot_matrix_covers_every_declared_language():
    tool = _load_tool()
    declared = set(I18nService.SUPPORTED_LANGUAGES)
    assert set(tool.WINDOW_LANGS) == declared
    assert set(tool.DIALOG_LANGS) == declared


def test_screenshot_tool_runs_and_produces_shots(tmp_path):
    tool = _load_tool()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, str(TOOL), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )

    assert result.returncode == 0, (
        f"The utility exited with code {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    shots = sorted(p.name for p in tmp_path.glob("*.png"))
    expected = _expected_shots(tool)
    missing = sorted(expected - set(shots))
    unexpected = sorted(set(shots) - expected)
    assert not missing, f"Missing screenshots: {missing}"
    assert not unexpected, f"Unexpected screenshots: {unexpected}"

    empty = [name for name in shots if (tmp_path / name).stat().st_size == 0]
    assert not empty, f"Empty screenshots: {empty}"

    assert "Screenshots saved to" in result.stdout, (
        f"The utility did not report the final summary.\nstdout:\n{result.stdout}"
    )
