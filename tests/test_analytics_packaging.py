import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_cli_entrypoint_and_build_backend_metadata():
    script = """
import sys
import tomllib
from pathlib import Path
metadata = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
assert metadata['project']['scripts']['srt4u'] == 'application.cli:main'
assert metadata['build-system']['build-backend'] == 'setuptools.build_meta'
try:
    import setuptools.build_meta
except ModuleNotFoundError:
    print('setuptools build backend unavailable in this environment')
else:
    print('setuptools build backend available')
assert 'PyQt6' not in sys.modules
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
    assert result.stdout.strip() in {
        "setuptools build backend unavailable in this environment",
        "setuptools build backend available",
    }
