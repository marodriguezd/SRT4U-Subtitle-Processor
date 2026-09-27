"""
Test de humo para `tools/regenerate_screenshots.py`: ejecuta la utilidad real
en un subproceso (plataforma offscreen) para evitar que se degrade con el tiempo.
"""

import os
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "regenerate_screenshots.py"

# 3 lenguas de ventana × 2 temas × 3 páginas + burn_en + progress_en + burnprogress_en
MIN_EXPECTED_SHOTS = 21
EXPECTED_SHOTS = [
    "home_en_dark.png",
    "home_de_light.png",
    "settings_en_dark.png",
    "settings_pt_light.png",
    "about_de_dark.png",
    "burn_en.png",
    "progress_en.png",
    "burnprogress_en.png",
]


def test_screenshot_tool_runs_and_produces_shots(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, str(TOOL), "--out", str(tmp_path), "--langs", "en"],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )

    assert result.returncode == 0, (
        f"La utilidad terminó con código {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    shots = sorted(p.name for p in tmp_path.glob("*.png"))
    assert len(shots) >= MIN_EXPECTED_SHOTS, (
        f"Se esperaban >= {MIN_EXPECTED_SHOTS} capturas y hubo {len(shots)}: {shots}"
    )

    missing = [name for name in EXPECTED_SHOTS if name not in shots]
    assert not missing, f"Capturas ausentes: {missing} (obtenidas: {shots})"

    empty = [name for name in shots if (tmp_path / name).stat().st_size == 0]
    assert not empty, f"Capturas vacías: {empty}"

    assert "Capturas guardadas" in result.stdout, (
        f"La utilidad no reportó el resumen final.\nstdout:\n{result.stdout}"
    )
