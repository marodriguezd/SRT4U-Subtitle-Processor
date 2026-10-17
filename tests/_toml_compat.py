"""TOML parsing that works on the declared Python >=3.10 floor.

``tomllib`` entered the standard library in Python 3.11 only; on 3.10 the
``dev`` extra provides ``tomli`` (same API), so the coherence, packaging and
hardening guards can read ``pyproject.toml`` there too. Keeping the fallback
in one module avoids three copies silently drifting apart.
"""

try:
    import tomllib as _toml
except ModuleNotFoundError:  # Python 3.10
    import tomli as _toml  # type: ignore[no-redef]


def load(path):
    """Parse a TOML file from a path (same contract as ``tomllib.load``)."""
    with open(path, "rb") as handle:
        return _toml.load(handle)
