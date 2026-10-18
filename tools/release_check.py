#!/usr/bin/env python3
"""Release tag gate: stable format + tag/pyproject version match.

The release job runs this before publishing, so a tag such as ``v1.4.8``,
``v2.0.0`` or ``v1.4.9-rc1`` can never produce a stable GitHub Release.
Deliberately minimal policy — this project has no prerelease convention:

* the tag must be ``vMAJOR.MINOR.PATCH`` (no prerelease/build suffixes);
* the tag version must equal ``project.version`` in ``pyproject.toml``, the
  single version source (``test_single_product_version_everywhere`` guards
  the rest of the chain: CLI, API, GUI, i18n).

Exit codes: ``0`` = publish allowed, ``1`` = refuse. The reason goes to
stderr; a success line goes to stdout.
"""

import re
import sys
from pathlib import Path

STABLE_TAG_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def project_version(pyproject_path: Path) -> str:
    """Read ``project.version`` from pyproject.toml (stdlib only)."""
    text = pyproject_path.read_text(encoding="utf-8")
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10: fall back to a scoped regex
        section = re.search(r"(?ms)^\[project\]$.*?(?=^\[|\Z)", text)
        source = section.group(0) if section else text
        match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', source, re.M)
        if not match:
            raise SystemExit(
                "pyproject.toml: no [project].version entry found"
            ) from None
        return match.group(1)
    with pyproject_path.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def check_tag(tag: str, pyproject_path: Path) -> str | None:
    """Return a refusal reason, or ``None`` when the tag may be published."""
    if not STABLE_TAG_RE.fullmatch(tag):
        return (
            f"the tag {tag!r} is not a stable vMAJOR.MINOR.PATCH version; "
            "pre-releases (e.g. v1.4.9-rc1) are not published as stable"
        )
    expected = f"v{project_version(pyproject_path)}"
    if tag != expected:
        return (
            f"the tag {tag!r} does not match the project version "
            f"({expected} in pyproject.toml)"
        )
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: release_check.py vX.Y.Z", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent.parent
    reason = check_tag(argv[1], root / "pyproject.toml")
    if reason is not None:
        print(f"release refused: {reason}", file=sys.stderr)
        return 1
    print(f"tag {argv[1]} verified against pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
